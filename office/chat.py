"""Conversations with the team. Each agent keeps an append-only thread on disk.

A thread holds two things: `history`, exactly what Claude saw and said (thinking and tool blocks
included, passed back unchanged), and `feed`, what the office shows: your messages, the agent's
replies and the updates it posts to you on its own.
"""

import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import anthropic

import llm
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
        # what each AI saw and said, kept separately: Claude and a local model use different formats
        self.histories = data.get("histories") or {"claude": data.get("history", [])}
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

    @property
    def history(self):
        return self.histories.setdefault("claude", [])

    @history.setter
    def history(self, value):
        self.histories["claude"] = value

    def trim(self):
        """Drop old messages from the front, at a point where a new exchange starts."""
        for history in self.histories.values():
            while len(history) > MAX_HISTORY:
                cut = next((i for i in range(1, len(history)) if _starts_exchange(history[i])), None)
                if cut is None:
                    break
                del history[:cut]

    def save(self):
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(json.dumps({
                "histories": self.histories, "feed": self.feed, "read_upto": self.read_upto,
                "pending": self.pending, "attention": self.attention,
            }, ensure_ascii=False))  # fmt: skip
            tmp.replace(self.path)


def _starts_exchange(message):
    return message["role"] == "user" and isinstance(message["content"], str)


@dataclass
class Step:
    texts: list  # what the agent said
    calls: list  # tools it wants to use: (call id, name, arguments)
    message: dict  # the assistant message to keep in the history, unchanged
    note: str = ""


class ClaudeEngine:
    """Claude through the Anthropic API (paid). Its turns are kept exactly as returned."""

    name = "claude"

    def __init__(self, client=None):
        self.client = client

    def step(self, agent, history):
        response = (self.client or anthropic.Anthropic()).beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=[{"type": "text", "text": agent.system, "cache_control": {"type": "ephemeral"}}],
            tools=agent.tools,
            messages=history,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},
            cache_control={"type": "ephemeral"},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            sorry = "Sorry, I can't help with that one."
            return Step([sorry], [], {"role": "assistant", "content": [{"type": "text", "text": sorry}]})
        message = {"role": "assistant", "content": [b.to_dict(mode="json", exclude_none=True) for b in response.content]}
        texts = [b.text.strip() for b in response.content if b.type == "text" and b.text.strip()]
        calls = [(b.id, b.name, b.input) for b in response.content if b.type == "tool_use"]
        note = "(I got cut off there. Ask me to continue.)" if response.stop_reason == "max_tokens" else ""
        return Step(texts, calls if response.stop_reason == "tool_use" else [], message, note)

    def results(self, outcomes):
        blocks = [
            {"type": "tool_result", "tool_use_id": call_id, "content": content, **({"is_error": True} if error else {})}
            for call_id, _, content, error in outcomes
        ]
        return [{"role": "user", "content": blocks}]

    def explain(self, error):
        if "authentication" in str(error).lower():
            return "set ANTHROPIC_API_KEY and restart the office (or leave it unset to use the free local AI)."
        return f"couldn't reach Claude: {error}"


class OllamaEngine:
    """A free local model through Ollama, running on your own computer."""

    name = "ollama"

    def __init__(self, session=None):
        self.session = session

    def step(self, agent, history):
        tools = [
            {"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
            for t in agent.tools
        ]
        system = {"role": "system", "content": agent.system}
        reply = llm.ollama_chat([system, *history], tools=tools, session=self.session)
        content = llm.strip_thinking(reply.get("content") or "")
        message = {"role": "assistant", "content": content}
        calls = []
        if reply.get("tool_calls"):
            message["tool_calls"] = reply["tool_calls"]
            for i, call in enumerate(reply["tool_calls"]):
                args = call["function"].get("arguments") or {}
                calls.append((f"call_{i}", call["function"]["name"], json.loads(args) if isinstance(args, str) else args))
        return Step([content] if content else [], calls, message)

    def results(self, outcomes):
        return [{"role": "tool", "tool_name": name, "content": content} for _, name, content, _ in outcomes]

    def explain(self, error):
        return str(error)


class Office:
    def __init__(self, team, data_dir="office_data", claude=None, engine=None):
        self.team = team
        if engine is None:
            engine = ClaudeEngine(claude) if claude is not None or llm.provider() == "claude" else OllamaEngine()
        self.engine = engine
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
            uploads = getattr(agent.desk, "uploads", lambda item: None)
            state["needs_clips"] = [i["id"] for i in items if i["status"] == "approved" and uploads(i) is not None
                                    and not all(uploads(i))]  # fmt: skip
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
            if new["needs_clips"]:
                lines.append("Approved, and waiting for your clips: copy each prompt into a free AI video site "
                             "(e.g. Dreamina), then Add clip on the card: "
                             + " ".join(f"[[{tag}:{i}]]" for i in new["needs_clips"][:5]))  # fmt: skip
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
        agent, thread, engine = self.team[key], self.threads[key], self.engine
        history = thread.histories.setdefault(engine.name, [])
        content = f"Message from {sender}:\n{text}" if sender else text
        with thread.lock:
            if thread.pending:
                updates = "\n".join(f"- {u}" for u in thread.pending)
                content = f"[Office updates]\n{updates}\n\n{content}"
                thread.pending = []
        thread.trim()
        history.append({"role": "user", "content": content})
        reply = []
        self.status[key] = "thinking"
        try:
            for _ in range(MAX_STEPS):
                step = engine.step(agent, history)
                history.append(step.message)
                for text_part in step.texts:
                    thread.add("agent", text_part)
                    reply.append(text_part)
                if step.note:
                    thread.add("agent", step.note)
                thread.save()
                if not step.calls:
                    break
                outcomes = []
                for call_id, name, args in step.calls:
                    self.status[key] = TOOL_STATUS.get(name, "working")
                    try:
                        outcomes.append((call_id, name, agent.run(name, args), False))
                    except Exception as e:  # the agent sees the error and can explain or retry
                        outcomes.append((call_id, name, f"Error: {e}", True))
                    self.status[key] = "thinking"
                history.extend(engine.results(outcomes))
                thread.save()
            else:
                thread.add("agent", "(I stopped after a lot of steps. Tell me how you'd like to continue.)")
        except Exception as e:  # no API key, Ollama not running, network... the office keeps running
            logging.exception("%s's turn failed", agent.name)
            thread.add("system", f"{agent.name} can't think right now: {engine.explain(e)}")
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
