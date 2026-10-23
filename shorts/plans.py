"""The AI plans short videos: hook, shots, on-screen text, voiceover and caption.

Shots are either free stock clips from Pexels found by a search query (VIDEO_SOURCE=stock, the
default) or AI clips made with Higgsfield from an image and a motion prompt (VIDEO_SOURCE=higgsfield).
"""

import os
from datetime import date

import llm
from x_agent.brain import WEB_SEARCH, ask
from x_agent.queue import PostQueue

CAPTION_LIMIT = 2200  # TikTok's and Instagram's caption limit
MAX_HASHTAGS = 30  # Instagram rejects captions with more
WORDS_PER_SECOND = 2.5  # comfortable voiceover pace

RULES = """\
You plan short vertical videos for the {platform} account described in the profile below. Each
video is {shots} clips of {seconds} seconds ({total} seconds in total). {visuals} {finish}

Rules:
- Never invent facts. Statistics, quotes, dates and claims about the world must come from a
  source you found with web search (put its URL in "sources") or be left out. Claims about the
  owner must be supported by the profile; don't add achievements, numbers or experiences.
- If the owner should check something before publishing, say exactly what in "fact_check".
  Otherwise leave it empty.
{visual_rules}
- All words go in "on_screen_text" (a few words per shot) and "voiceover". The first shot's
  on-screen text is the hook and must make someone stop scrolling within two seconds.
- The voiceover is at most {words} words so it fits the video when read at a natural pace.
- The caption is one or two plain sentences plus 3 to 5 relevant hashtags, under 300 characters.
- Write like a thoughtful person, not a marketer: no buzzwords, no clickbait you can't pay off.

Profile:
{profile}"""

VISUALS = {
    "stock": (
        "The clips are real stock videos from a free stock site, one found with your search query for each shot; "
        "the joke comes from your on-screen text over the clip.",
        """\
- Each shot's search_query is 2 to 5 plain words naming one animal doing one visible thing, like
  "cat knocking cup off table", "goat standing on rock" or "dog wearing sunglasses". Common,
  concrete scenes find good clips. No people, brands or anything a stock site wouldn't have.
- The three shots of a video are three different scenes with three different queries. Vary the
  animal from video to video: dogs, goats, ducks, parrots, horses, cows, monkeys, penguins,
  hamsters and more, not only cats.
- Write the on-screen text so the joke still works if the clip only roughly matches the query.""",
    ),
    "higgsfield": (
        "The clips are AI-generated with Higgsfield: first an image from your image prompt, then a "
        "clip that animates it from your motion prompt.",
        """\
- Image prompts describe a single 9:16 vertical scene: subject, setting, light, style. They
  must not ask for any text, numbers, charts with values, logos or brand names (image models
  render these badly), and never show a real, identifiable person. Use people only as anonymous
  figures (hands, silhouettes, backs, crowds).
- Motion prompts describe one clear action of the subject (the beat of the joke, if it is one)
  and, at most, one simple camera movement.""",
    ),
}
SHOT_FIELDS = {
    "stock": {"search_query": {"type": "string"}},
    "higgsfield": {"image_prompt": {"type": "string"}, "motion_prompt": {"type": "string"}},
}


def video_source():
    source = (os.environ.get("VIDEO_SOURCE") or "stock").strip().lower()
    if source not in VISUALS:
        raise ValueError(f"VIDEO_SOURCE must be one of {', '.join(VISUALS)}, not {source!r}")
    return source


def schemas(source=None):
    """(all concepts, one revision) JSON schemas for the given video source."""
    fields = {**SHOT_FIELDS[source or video_source()], "on_screen_text": {"type": "string"}}
    shot = {"type": "object", "properties": fields, "required": list(fields), "additionalProperties": False}
    plan_fields = {
        "shots": {"type": "array", "items": shot},
        "voiceover": {"type": "string"},
        "caption": {"type": "string"},
        "sources": {"type": "array", "items": {"type": "string"}, "description": "URLs backing factual claims"},
        "fact_check": {"type": "string", "description": "What the owner must verify first; empty if nothing"},
    }
    concept = {
        "type": "object",
        "properties": {
            "pillar": {"type": "string", "description": "Content pillar from the profile"},
            "hook": {"type": "string", "description": "The idea in one line"},
            **plan_fields,
        },
        "required": ["pillar", "hook", *plan_fields],
        "additionalProperties": False,
    }
    concepts = {
        "type": "object",
        "properties": {"concepts": {"type": "array", "items": concept}},
        "required": ["concepts"],
        "additionalProperties": False,
    }
    revision = {"type": "object", "properties": plan_fields, "required": list(plan_fields), "additionalProperties": False}
    return concepts, revision


class VideoQueue(PostQueue):
    """draft -> approved -> rendered -> sent (TikTok inbox) or posted (Instagram)."""

    STATUSES = ("draft", "approved", "rendered", "sent", "posted", "rejected", "failed")

    def _content(self, concept):
        return {k: concept[k] for k in ("shots", "voiceover", "caption")}


def generate(platform, profile, count, theme="", avoid=(), use_web=True, client=None, unattended=False, searches=()):
    request = [f"Today is {date.today():%d %B %Y}. Plan {count} videos."]
    request.append(f"Focus on: {theme}" if theme else "Spread them across the content pillars.")
    use_web = use_web and (client is not None or llm.web_search_available())
    if use_web:
        request.append("If it helps, search the web for recent news or trends worth reacting to before you plan.")
    if avoid:
        request.append("Already used, don't repeat these:\n" + "\n".join(f"- {h}" for h in avoid))
    if video_source() == "stock":
        request.append(
            f"Give each of the {count} videos a different animal, and every shot its own search query "
            "(three different scenes, not the same clip three times)."
        )
        if searches:
            request.append(
                "Recent videos already used these clip searches. Pick other animals and scenes, so the "
                "channel doesn't keep showing the same footage:\n" + "\n".join(f"- {q}" for q in searches)
            )
    if unattended:
        request.append(
            "These are published automatically, without the owner reviewing them. Prefer ideas that are "
            "fully supported by the profile or by sources you found. Anything that would still need checking "
            "must be listed in fact_check; those are held back for the owner."
        )
    tools = [WEB_SEARCH] if use_web else []
    return ask(client, _system(platform, profile), "\n\n".join(request), schemas()[0], tools)["concepts"]


def recent_searches(items, n=30):
    """The stock-clip searches of the latest videos, newest last."""
    queries = [s["search_query"] for it in items[-12:] for s in it.get("shots", []) if s.get("search_query")]
    return list(dict.fromkeys(queries))[-n:]


def revise(platform, profile, item, feedback, client=None):
    plan = {k: item[k] for k in ("shots", "voiceover", "caption", "sources", "fact_check")}
    request = f"Idea: {item['hook']}\n\nCurrent plan (JSON): {plan}\n\nRewrite it. Feedback: {feedback}"
    return ask(client, _system(platform, profile), request, schemas()[1])


def problems(platform, item):
    shots, seconds = platform.shots, platform.seconds
    out = []
    if len(item["shots"]) != shots:
        out.append(f"{len(item['shots'])} shots planned, {shots} expected")
    words = len(item["voiceover"].split())
    if words > _max_words(shots, seconds):
        out.append(f"voiceover is {words} words, {_max_words(shots, seconds)} fit in {shots * seconds}s")
    if len(item["caption"]) > CAPTION_LIMIT:
        out.append(f"caption is {len(item['caption'])} characters (limit {CAPTION_LIMIT})")
    hashtags = item["caption"].count("#")
    if hashtags > MAX_HASHTAGS:
        out.append(f"caption has {hashtags} hashtags (limit {MAX_HASHTAGS})")
    for i, shot in enumerate(item["shots"], 1):
        words = len(shot["on_screen_text"].split())
        if platform.screen_words and words > platform.screen_words:
            out.append(f"shot {i} on-screen text is {words} words ({platform.screen_words} fit on screen)")
    return out


def _max_words(shots, seconds):
    return int(shots * seconds * WORDS_PER_SECOND)


def _system(platform, profile):
    shots, seconds = platform.shots, platform.seconds
    visuals, visual_rules = VISUALS[video_source()]
    return RULES.format(
        visuals=visuals,
        visual_rules=visual_rules,
        platform=platform.title,
        shots=shots,
        seconds=seconds,
        total=shots * seconds,
        finish=platform.finish,
        words=_max_words(shots, seconds),
        profile=profile,
    )
