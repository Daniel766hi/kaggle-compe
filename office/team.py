"""Who works in the office: a head of content and one producer per channel."""

import json
from dataclasses import dataclass, field
from typing import Callable

from . import desks

RULES = """\
Rules of the office:
- You can read, draft, revise and reject. You cannot approve or publish: the owner does that with
  the buttons on each item card. When something is ready, say so and show its card.
- To show an item, write its tag on its own, like [[{key}:12]]. The office turns it into a card with
  the buttons. Show cards rather than pasting long text.
- Drafting costs API credits: draft at most 5 items at a time unless the owner asks for more.
  Rendering videos costs more, and only the owner starts it.
- Never invent facts about the owner or the world. Pass on any fact-check notes honestly.
- A message starting with "[Office updates]" lists updates you posted earlier while the owner was
  away; take them into account.
- Plans with video prompts are made from clips the owner creates on a free AI video website: after
  approving, they copy each shot's prompt there and use Add clip on the card. Remind them kindly.
- Write like a colleague on a work chat: short, friendly, concrete. No headings."""

CHANNEL = """\
You are {name}, the {role} in a small AI content office. You work for the owner, the person
chatting with you, and you look after the {title} content queue. {about}

{rules}"""

HEAD = """\
You are Maya, Head of Content in a small AI content office. You work for the owner, the person
chatting with you. Your team: Raka writes for X (the owner's professional profile), Sari produces
TikTok videos and Bima produces Instagram Reels (both are a funny AI animal channel). Use
team_overview to see where everything stands and ask_teammate to hand work to the right person,
then report back briefly. You plan and coordinate; the producers do the drafting.

{rules}
Tags for other desks look like [[x:3]], [[tiktok:5]] or [[instagram:2]]."""

STATUS_FILTER = ["waiting", "draft", "approved", "rendered", "sent", "posted", "failed", "rejected", "all"]


def _tool(name, description, properties=None):
    return {
        "name": name,
        "description": description,
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": properties or {},
            "required": list(properties or {}),
            "additionalProperties": False,
        },
    }


CHANNEL_TOOLS = [
    _tool("list_items", "List items in your queue. 'waiting' = drafts, approved, rendered and failed items.",
          {"status": {"type": "string", "enum": STATUS_FILTER}}),
    _tool("show_item", "Everything about one item: full text or shots, caption, sources, fact-check notes.",
          {"id": {"type": "integer"}}),
    _tool("create_drafts", "Research and draft new items into the queue (uses API credits). Empty theme = mix.",
          {"count": {"type": "integer", "enum": [1, 2, 3, 4, 5]}, "theme": {"type": "string"}}),
    _tool("revise_item", "Rewrite a draft following feedback. It goes back to draft for the owner to approve.",
          {"id": {"type": "integer"}, "feedback": {"type": "string"}}),
    _tool("reject_item", "Reject an item the owner doesn't want.", {"id": {"type": "integer"}}),
]  # fmt: skip


@dataclass
class Agent:
    key: str
    name: str
    role: str
    emoji: str
    color: str
    system: str
    tools: list
    desk: object = None
    run: Callable = field(default=None, repr=False)  # (tool name, input) -> result text


def channel_agent(key, name, role, emoji, color, desk, about):
    system = CHANNEL.format(name=name, role=role, title=desk.title, about=about, rules=RULES.format(key=desk.key))

    def run(tool, args):
        if tool == "list_items":
            items = desk.items(args["status"])
            return _json([desks.summary(desk, i) for i in items[-30:]] or "nothing in that list")
        if tool == "show_item":
            return _json(desks.summary(desk, desk.item(args["id"]), full=True))
        if tool == "create_drafts":
            added = desk.create_drafts(args["count"], args["theme"])
            return _json({"added": [desks.summary(desk, i) for i in added]})
        if tool == "revise_item":
            return _json(desks.summary(desk, desk.revise(args["id"], args["feedback"]), full=True))
        if tool == "reject_item":
            desk.reject(args["id"])
            return f"#{args['id']} rejected"
        raise ValueError(f"unknown tool {tool}")

    return Agent(key, name, role, emoji, color, system, CHANNEL_TOOLS, desk, run)


def build_team(x_desk, tiktok_desk, instagram_desk):
    team = {
        "raka": channel_agent("raka", "Raka", "X writer", "✍️", "#3b82f6", x_desk,
                              "Posts are written from the owner's professional profile (x_agent/profile.md)."),
        "sari": channel_agent("sari", "Sari", "TikTok producer", "🎬", "#ec4899", tiktok_desk,
                              "Videos are funny, ridiculous AI animal sketches (shorts/profile.md)."),
        "bima": channel_agent("bima", "Bima", "Instagram Reels producer", "📸", "#f59e0b", instagram_desk,
                              "Reels are funny, ridiculous AI animal sketches (shorts/profile.md)."),
    }  # fmt: skip
    head_tools = [
        _tool("team_overview", "Counts per status for every channel, and what needs the owner."),
        _tool("ask_teammate", "Send a message to a teammate and get their reply. They can draft and revise.",
              {"teammate": {"type": "string", "enum": list(team)}, "message": {"type": "string"}}),
    ]  # fmt: skip
    team["maya"] = Agent("maya", "Maya", "Head of Content", "🧭", "#10b981", HEAD.format(rules=RULES.format(key="x")), head_tools)
    return team


def _json(value):
    return json.dumps(value, ensure_ascii=False, indent=1)
