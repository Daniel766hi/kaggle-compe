"""Claude writes the ideas and drafts.

Ideation can search the web (Anthropic's server-side web search) so posts can react to current
news and cite real sources. Output is constrained to a JSON schema, so the queue always gets
well-formed drafts.
"""

import json
import os
from datetime import date

import anthropic

import llm

from . import text

MODEL = os.environ.get("X_AGENT_MODEL") or "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"  # retry on another model if a request is declined
MAX_CONTINUATIONS = 5  # web search may pause a long turn; resume it at most this many times
WEB_SEARCH = {"type": "web_search_20260209", "name": "web_search", "max_uses": 6}

RULES = """\
You write posts for the X (Twitter) account described in the profile below. The account owner
reviews every draft before it is published.

Rules:
- Never invent facts. Statistics, quotes, dates and claims about the world must come from a
  source you found with web search (put its URL in "sources") or be left out. Claims about the
  owner must be supported by the profile; don't add achievements, numbers or experiences.
- If the owner should check something before publishing (a number, a claim, a dataset
  finding they need to compute first), say exactly what in "fact_check". Otherwise leave it empty.
- Ideas based on the owner's own datasets describe what to look at or show, unless the actual
  finding is given to you; never state a finding you haven't been given.
- Never share confidential details about employers or organisations.
- Each post must fit in {limit} characters as X counts them (a link counts as 23, an emoji as 2).
- A thread is 2 to 5 posts, used only when one post isn't enough. Don't number posts or add 🧵.
- Write like a thoughtful person, not a marketer: no buzzwords, no engagement bait, at most one
  hashtag, no emoji unless it adds meaning.

Profile:
{profile}"""

POST_FIELDS = {
    "posts": {"type": "array", "items": {"type": "string"}, "description": "One post, or a thread in order"},
    "sources": {"type": "array", "items": {"type": "string"}, "description": "URLs backing factual claims"},
    "fact_check": {"type": "string", "description": "What the owner must verify first; empty if nothing"},
}
IDEA_SCHEMA = {
    "type": "object",
    "properties": {
        "pillar": {"type": "string", "description": "Content pillar from the profile"},
        "hook": {"type": "string", "description": "The idea in one line"},
        **POST_FIELDS,
    },
    "required": ["pillar", "hook", "posts", "sources", "fact_check"],
    "additionalProperties": False,
}
IDEAS_SCHEMA = {
    "type": "object",
    "properties": {"ideas": {"type": "array", "items": IDEA_SCHEMA}},
    "required": ["ideas"],
    "additionalProperties": False,
}
REVISION_SCHEMA = {
    "type": "object",
    "properties": POST_FIELDS,
    "required": list(POST_FIELDS),
    "additionalProperties": False,
}


class AgentError(RuntimeError):
    pass


def load_profile(path=None):
    path = path or os.environ.get("X_PROFILE") or os.path.join(os.path.dirname(__file__), "profile.md")
    with open(path, encoding="utf-8") as f:
        return f.read()


def generate_ideas(profile, count, theme="", avoid=(), use_web=True, client=None, unattended=False):
    """Return `count` ideas, each with ready-to-publish post text."""
    request = [f"Today is {date.today():%d %B %Y}. Suggest {count} post ideas and write each one out."]
    request.append(f"Focus on: {theme}" if theme else "Spread them across the content pillars.")
    use_web = use_web and (client is not None or llm.web_search_available())
    if use_web:
        request.append("Search the web for recent news or data worth reacting to before you write.")
    if avoid:
        request.append("Already used, don't repeat these:\n" + "\n".join(f"- {h}" for h in avoid))
    if unattended:
        request.append(
            "These are published automatically, without the owner reviewing them. Prefer ideas that are "
            "fully supported by the profile or by sources you found. Anything that would still need checking "
            "must be listed in fact_check; those are held back for the owner."
        )
    tools = [WEB_SEARCH] if use_web else []
    return ask(client, _system(profile), "\n\n".join(request), IDEAS_SCHEMA, tools)["ideas"]


def revise(profile, item, feedback, client=None):
    """Rewrite a queue item's posts following the feedback; returns posts, sources and fact_check."""
    current = "\n---\n".join(item["posts"])
    request = (
        f"Idea: {item['hook']}\n\nCurrent draft (posts separated by ---):\n{current}\n\n"
        f"Sources so far: {', '.join(item.get('sources', [])) or 'none'}\n\n"
        f"Rewrite it. Feedback: {feedback}"
    )
    return ask(client, _system(profile), request, REVISION_SCHEMA)


def _system(profile):
    return RULES.format(limit=text.max_chars(), profile=profile)


def ask(client, system, request, schema, tools=()):
    """One request whose answer must match `schema`; resumes paused web searches.

    Without a client, the free local model answers when it is the chosen AI (see llm.py).
    """
    if client is None and llm.provider() == "ollama":
        return llm.ollama_json(system, request, schema)
    client = client or anthropic.Anthropic()
    messages = [{"role": "user", "content": request}]
    for _ in range(MAX_CONTINUATIONS + 1):
        params = dict(
            model=MODEL,
            max_tokens=32000,
            system=system,
            messages=messages,
            thinking={"type": "adaptive"},
            output_config={"effort": "high", "format": {"type": "json_schema", "schema": schema}},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        if tools:
            params["tools"] = list(tools)
        with client.beta.messages.stream(**params) as stream:
            message = stream.get_final_message()
        if message.stop_reason != "pause_turn":
            break
        # The server paused mid-search; send its partial turn back and it resumes.
        messages = [messages[0], {"role": "assistant", "content": message.content}]
    else:
        raise AgentError("web search did not finish; try again or use --no-web")

    if message.stop_reason == "refusal":
        raise AgentError(f"Claude declined this request: {message.stop_details}")
    if message.stop_reason == "max_tokens":
        raise AgentError("the answer was cut off; ask for fewer ideas")
    return _parse_json(message.content)


def _parse_json(content):
    # The JSON answer is the text written after the last search call/result.
    last_tool = max((i for i, b in enumerate(content) if b.type not in ("text", "thinking")), default=-1)
    answer = "".join(b.text for b in content[last_tool + 1 :] if b.type == "text")
    try:
        return json.loads(answer)
    except json.JSONDecodeError as e:
        raise AgentError(f"could not read Claude's answer as JSON: {answer[:300]!r}") from e
