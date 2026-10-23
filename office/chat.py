"""Conversations with the team. Each agent keeps an append-only thread on disk.

A thread holds two things: `history`, exactly what Claude saw and said (thinking and tool blocks
included, passed back unchanged), and `feed`, what the office shows: your messages, the agent's
replies and the updates it posts to you on its own.
"""

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

import anthropic

from x_agent.brain import FALLBACK_BETA, MODEL

from . import desks

MAX_STEPS = 12  # tool calls per reply
MAX_HISTORY = 80  # messages kept for Claude; older ones are dropped from the front
TOOL_STATUS = {
    "list_items": "checking the queue",
    "show_item": "reading an item",
    "create_drafts": "drafting",
    "revise_item": "revising",
    "reject_item": "tidying the queue",
    "team_overview": "checking on the team",
    "ask_teammate": "talking to the team",
}


def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Thread:
    def __init__(self, path):
        self.path = Path(path)
        data = json.loads(self.path.read_text()) if self.path.exists() else {}
        self.history = data.get("history", [])
        self.feed = data.get("feed", [])
        self.read_upto = data.get("read_upto", 0)
        self.pending = data.get("pending", [])  # updates posted since the last conversation turn
        self.attention = data.get("attention", {})
        self.lock = threading.RLock()  # replies, check-ins and finished jobs may write at the same time

    def add(self, sender, text):
        with self.lock:
            entry = {"id": (self.feed[-1]["id"] + 1) if self.feed else 1, "time": now(), "from": sender, "text": text}
            self.feed.append(entry)
            return entry

    def unread(self):
        return sum(1 for e in self.feed if e["id"] > self.read_upto and e["from"] != "you")

    def trim(self):
        """Drop old messages from the front, at a point where a new exchange starts."""
        while len(self.history) > MAX_HISTORY:
            cut = next((i for i in range(1, len(self.history)) if _starts_exchange(self.history[i])), None)
            if cut is None:
                break
            del self.history[:cut]

    def save(self):
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(json.dumps({
                "history": self.history, "feed": self.feed, "read_upto": self.read_upto,
                "pending": self.pending, "attention": self.attention,
            }, ensure_ascii=False))  # fmt: skip
            tmp.replace(self.path)


def _starts_exchange(message):
    return message["role"] == "user" and isinstance(message["content"], str)


class Office:
    def __init__(self, team, data_dir="office_data", claude=None):
        self.team, self.claude = team, claude
        self.threads = {key: Thread(Path(data_dir) / f"{key}.json") for key in team}
        self.locks = {key: threading.Lock() for key in team}
        self.status = {key: "" for key in team}  # what each agent is doing right now
        self.checkin_lock = threading.Lock()
        team["maya"].run = self._head_tool

    # --- you -> agent ------------------------------------------------------------------------
    def say(self, key, text):
        """Your message to an agent; returns once the agent has replied."""
        with self.locks[key]:
            thread = self.threads[key]
            thread.add("you", text)
            thread.read_upto = thread.feed[-1]["id"]
            thread.save()
            return self._turn(key, text)

    # --- agent -> you ------------------------------------------------------------------------
    def notify(self, key, text):
        """An update the agent posts to you on its own."""
        thread = self.threads[key]
        with thread.lock:
            thread.add("agent", text)
            thread.pending.append(text)
            thread.save()

    def checkin(self):
        """Every producer looks at its queue and tells you about anything new that needs you."""
        with self.checkin_lock:
            self._checkin()

    def _checkin(self):
        for key, agent in self.team.items():
            if agent.desk is None:
                continue
            try:
                items = agent.desk.queue().items
            except Exception as e:  # a broken queue file must not stop the other desks
                logging.warning("check-in for %s failed: %s", key, e)
                continue
            thread, tag = self.threads[key], agent.desk.key
            state = {s: [i["id"] for i in items if i["status"] == s] for s in ("draft", "failed", "rendered")}
            seen = thread.attention
            new = {s: [i for i in ids if i not in seen.get(s, [])] for s, ids in state.items()}
            lines = []
            if new["draft"]:
                waiting = state["draft"]
                cards = " ".join(f"[[{tag}:{i}]]" for i in new["draft"][:5])
                lines.append(f"{len(waiting)} draft{'s' if len(waiting) > 1 else ''} waiting for your review: {cards}")
            if new["failed"]:
                lines.append("This didn't go out: " + " ".join(f"[[{tag}:{i}]]" for i in new["failed"][:5])
                             + " Want me to take a look?")  # fmt: skip
            if new["rendered"]:
                lines.append("Rendered and ready to watch: " + " ".join(f"[[{tag}:{i}]]" for i in new["rendered"][:5]))
            empty = not any(i["status"] in ("draft", "approved", "rendered") for i in items)
            if empty and not seen.get("told_empty"):
                lines.append("My queue is empty. Want me to draft a few ideas?")
            thread.attention = {**state, "told_empty": empty and (seen.get("told_empty") or bool(lines))}
            if lines:
                self.notify(key, "\n".join(lines))
            else:
                thread.save()

    # --- the conversation loop ---------------------------------------------------------------
    def _turn(self, key, text, sender=None):
        agent, thread = self.team[key], self.threads[key]
        content = f"Message from {sender}:\n{text}" if sender else text
        with thread.lock:
            if thread.pending:
                updates = "\n".join(f"- {u}" for u in thread.pending)
                content = f"[Office updates]\n{updates}\n\n{content}"
                thread.pending = []
        thread.trim()
        thread.history.append({"role": "user", "content": content})
        reply = []
        self.status[key] = "thinking"
        try:
            for _ in range(MAX_STEPS):
                response = (self.claude or anthropic.Anthropic()).beta.messages.create(
                    model=MODEL,
                    max_tokens=16000,
                    system=[{"type": "text", "text": agent.system, "cache_control": {"type": "ephemeral"}}],
                    tools=agent.tools,
                    messages=thread.history,
                    thinking={"type": "adaptive"},
                    output_config={"effort": "medium"},
                    cache_control={"type": "ephemeral"},
                    betas=[FALLBACK_BETA],
                    fallbacks="default",
                )
                if response.stop_reason == "refusal":
                    sorry = "Sorry, I can't help with that one."
                    thread.history.append({"role": "assistant", "content": [{"type": "text", "text": sorry}]})
                    thread.add("agent", sorry)
                    reply.append(sorry)
                    break
                thread.history.append({"role": "assistant", "content": [b.to_dict(mode="json", exclude_none=True) for b in response.content]})
                for block in response.content:
                    if block.type == "text" and block.text.strip():
                        thread.add("agent", block.text.strip())
                        reply.append(block.text.strip())
                thread.save()
                if response.stop_reason == "max_tokens":
                    thread.add("agent", "(I got cut off there. Ask me to continue.)")
                    break
                if response.stop_reason != "tool_use":
                    break
                results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    self.status[key] = TOOL_STATUS.get(block.name, "working")
                    try:
                        results.append({"type": "tool_result", "tool_use_id": block.id, "content": agent.run(block.name, block.input)})
                    except Exception as e:  # the agent sees the error and can explain or retry
                        results.append({"type": "tool_result", "tool_use_id": block.id, "content": f"Error: {e}", "is_error": True})
                    self.status[key] = "thinking"
                thread.history.append({"role": "user", "content": results})
                thread.save()
            else:
                thread.add("agent", "(I stopped after a lot of steps. Tell me how you'd like to continue.)")
        except Exception as e:  # no API key, network, rate limit... the office keeps running
            logging.exception("%s's turn failed", agent.name)
            if "authentication" in str(e).lower():
                thread.add("system", f"{agent.name} can't reach Claude yet: set ANTHROPIC_API_KEY and restart the office.")
            else:
                thread.add("system", f"{agent.name} couldn't reach Claude: {e}")
        finally:
            self.status[key] = ""
            thread.save()
        return "\n\n".join(reply)

    # --- Maya's tools ------------------------------------------------------------------------
    def _head_tool(self, tool, args):
        if tool == "team_overview":
            overview = {}
            for key, agent in self.team.items():
                if agent.desk is not None:
                    waiting = agent.desk.items("waiting")
                    overview[f"{agent.name} ({agent.desk.title})"] = {
                        "counts": agent.desk.counts(),
                        "needs_owner": [desks.summary(agent.desk, i) for i in waiting if i["status"] in ("draft", "failed", "rendered")][:10],
                    }  # fmt: skip
            return json.dumps(overview, ensure_ascii=False, indent=1)
        if tool == "ask_teammate":
            key = args["teammate"]
            with self.locks[key]:
                thread = self.threads[key]
                thread.add("maya", args["message"])
                thread.save()
                answer = self._turn(key, args["message"], sender="Maya (Head of Content)")
            return answer or f"{self.team[key].name} didn't reply."
        raise ValueError(f"unknown tool {tool}")
