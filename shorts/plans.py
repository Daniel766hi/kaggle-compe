"""Claude plans short videos: hook, shots for Higgsfield, on-screen text, voiceover and caption."""

from datetime import date

from x_agent.brain import WEB_SEARCH, ask
from x_agent.queue import PostQueue

CAPTION_LIMIT = 2200  # TikTok's and Instagram's caption limit
MAX_HASHTAGS = 30  # Instagram rejects captions with more
WORDS_PER_SECOND = 2.5  # comfortable voiceover pace

RULES = """\
You plan short vertical videos for the {platform} account of the person described in the profile
below. Each video is {shots} AI-generated clips of {seconds} seconds ({total} seconds in total),
made with Higgsfield: first an image from your image prompt, then a clip that animates it from
your motion prompt. {finish}

Rules:
- Never invent facts. Statistics, quotes, dates and claims about the world must come from a
  source you found with web search (put its URL in "sources") or be left out. Claims about the
  owner must be supported by the profile; don't add achievements, numbers or experiences.
- If the owner should check something before publishing, say exactly what in "fact_check".
  Otherwise leave it empty.
- Image prompts describe a single 9:16 vertical scene: subject, setting, light, style. They
  must not ask for any text, numbers, charts with values, logos or brand names (image models
  render these badly), and never show a real, identifiable person. Use people only as anonymous
  figures (hands, silhouettes, backs, crowds).
- Motion prompts describe one simple movement of the camera or subject.
- All words go in "on_screen_text" (a few words per shot) and "voiceover". The first shot's
  on-screen text is the hook and must make someone stop scrolling within two seconds.
- The voiceover is at most {words} words so it fits the video when read at a natural pace.
- The caption is one or two plain sentences plus 3 to 5 relevant hashtags, under 300 characters.
- Write like a thoughtful person, not a marketer: no buzzwords, no clickbait you can't pay off.

Profile:
{profile}"""

SHOT = {
    "type": "object",
    "properties": {
        "image_prompt": {"type": "string"},
        "motion_prompt": {"type": "string"},
        "on_screen_text": {"type": "string"},
    },
    "required": ["image_prompt", "motion_prompt", "on_screen_text"],
    "additionalProperties": False,
}
PLAN_FIELDS = {
    "shots": {"type": "array", "items": SHOT},
    "voiceover": {"type": "string"},
    "caption": {"type": "string"},
    "sources": {"type": "array", "items": {"type": "string"}, "description": "URLs backing factual claims"},
    "fact_check": {"type": "string", "description": "What the owner must verify first; empty if nothing"},
}
CONCEPT_SCHEMA = {
    "type": "object",
    "properties": {
        "pillar": {"type": "string", "description": "Content pillar from the profile"},
        "hook": {"type": "string", "description": "The idea in one line"},
        **PLAN_FIELDS,
    },
    "required": ["pillar", "hook", *PLAN_FIELDS],
    "additionalProperties": False,
}
CONCEPTS_SCHEMA = {
    "type": "object",
    "properties": {"concepts": {"type": "array", "items": CONCEPT_SCHEMA}},
    "required": ["concepts"],
    "additionalProperties": False,
}
REVISION_SCHEMA = {
    "type": "object",
    "properties": PLAN_FIELDS,
    "required": list(PLAN_FIELDS),
    "additionalProperties": False,
}


class VideoQueue(PostQueue):
    """draft -> approved -> rendered -> sent (TikTok inbox) or posted (Instagram)."""

    STATUSES = ("draft", "approved", "rendered", "sent", "posted", "rejected", "failed")

    def _content(self, concept):
        return {k: concept[k] for k in ("shots", "voiceover", "caption")}


def generate(platform, profile, count, theme="", avoid=(), use_web=True, client=None, unattended=False):
    request = [f"Today is {date.today():%d %B %Y}. Plan {count} videos."]
    request.append(f"Focus on: {theme}" if theme else "Spread them across the content pillars.")
    if use_web:
        request.append("Search the web for recent news or data worth reacting to before you plan.")
    if avoid:
        request.append("Already used, don't repeat these:\n" + "\n".join(f"- {h}" for h in avoid))
    if unattended:
        request.append(
            "These are published automatically, without the owner reviewing them. Prefer ideas that are "
            "fully supported by the profile or by sources you found. Anything that would still need checking "
            "must be listed in fact_check; those are held back for the owner."
        )
    tools = [WEB_SEARCH] if use_web else []
    return ask(client, _system(platform, profile), "\n\n".join(request), CONCEPTS_SCHEMA, tools)["concepts"]


def revise(platform, profile, item, feedback, client=None):
    plan = {k: item[k] for k in ("shots", "voiceover", "caption", "sources", "fact_check")}
    request = f"Idea: {item['hook']}\n\nCurrent plan (JSON): {plan}\n\nRewrite it. Feedback: {feedback}"
    return ask(client, _system(platform, profile), request, REVISION_SCHEMA)


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
    return RULES.format(
        platform=platform.title,
        shots=shots,
        seconds=seconds,
        total=shots * seconds,
        finish=platform.finish,
        words=_max_words(shots, seconds),
        profile=profile,
    )
