"""Commands shared by the TikTok and Instagram agents. Each agent describes itself as a Platform."""

import argparse
import logging
import os
import shlex
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import llm
import local_env
from x_agent.brain import load_profile

from . import images, plans, render
from .plans import VideoQueue

WAITING = ("draft", "approved", "rendered", "failed")


@dataclass
class Platform:
    name: str  # module is <name>_agent; files are content/<name>_queue.json and build/<name>/
    title: str  # shown to Claude and in messages
    env: str  # prefix of the settings variables, e.g. TIKTOK -> TIKTOK_SHOTS
    finish: str  # tells Claude what happens to the video after it is rendered
    published_status: str  # "sent" (to an inbox) or "posted"
    publish: Callable  # (client, video_path, item) -> fields to record on the item ("status" overrides)
    client: Callable  # () -> API client built from environment variables
    errors: tuple  # exceptions that mean publishing failed
    done: Callable  # (item) -> message after publishing
    burn_text: bool = False  # on-screen text and an audio track rendered into the video
    screen_words: int = 0  # max words of on-screen text per shot (0: no limit)
    extra_commands: Callable = field(default=lambda sub: None)  # adds platform-only commands

    def setting(self, key, default):
        return os.environ.get(f"{self.env}_{key}") or default

    @property
    def shots(self):
        return int(self.setting("SHOTS", 3))

    @property
    def seconds(self):
        """Seconds per shot: 3 x 5 s by default (Higgsfield bills video per second)."""
        return int(self.setting("CLIP_SECONDS", 5))

    @property
    def profile(self):
        """The channel the videos are made for (shorts/profile.md unless <ENV>_PROFILE is set)."""
        return load_profile(self.setting("PROFILE", str(Path(__file__).with_name("profile.md"))))

    def queue(self, path=None):
        return VideoQueue(path or self.setting("QUEUE", f"content/{self.name}_queue.json"))


def main(platform, doc, argv=None):
    local_env.load()  # keys saved by the setup script, when run on your computer
    if argv is None:
        argv = sys.argv[1:] or shlex.split(platform.setting("AGENT_COMMAND", "list"))
    args = _parser(platform, doc).parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    queue = platform.queue(args.queue)
    try:
        return args.run(platform, queue, args) or 0
    finally:
        queue.save()  # keep rendered clips and publish ids even if a later step failed


def _parser(platform, doc):
    parser = argparse.ArgumentParser(description=doc, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--queue", help=f"queue file (default: ${platform.env}_QUEUE or content/{platform.name}_queue.json)")
    sub = parser.add_subparsers(required=True, metavar="command")

    p = sub.add_parser("ideas", help="research and plan new videos")
    p.add_argument("--count", type=int, default=3)
    p.add_argument("--theme", default="")
    p.add_argument("--no-web", action="store_true", help="don't search the web")
    p.set_defaults(run=cmd_ideas)

    p = sub.add_parser("list", help="show queue items")
    p.add_argument("--status", choices=[*VideoQueue.STATUSES, "all"])
    p.set_defaults(run=cmd_list)

    p = sub.add_parser("show", help="show one plan in full")
    p.add_argument("id", type=int)
    p.set_defaults(run=cmd_show)

    p = sub.add_parser("revise", help="have Claude rework a plan with your feedback")
    p.add_argument("id", type=int)
    p.add_argument("feedback")
    p.set_defaults(run=cmd_revise)

    for name, status in (("approve", "approved"), ("reject", "rejected")):
        p = sub.add_parser(name, help=f"mark plans {status}")
        p.add_argument("ids", type=int, nargs="+")
        p.set_defaults(run=cmd_set_status, status=status)

    p = sub.add_parser("make", help=f"render an approved plan and publish it to {platform.title}")
    p.add_argument("id", type=int)
    p.add_argument("--no-upload", action="store_true", help="only render, to preview the mp4")
    p.add_argument("--new-clips", action="store_true", help="stock videos: replace the clips with different ones")
    p.set_defaults(run=cmd_make)

    p = sub.add_parser("autopilot", help="top up plans, then make the oldest approved one")
    p.add_argument("--min-drafts", type=int, default=int(platform.setting("MIN_DRAFTS", 3)))
    p.add_argument("--count", type=int, default=3, help="plans to generate when topping up")
    p.set_defaults(run=cmd_autopilot)

    platform.extra_commands(sub)
    return parser


def cmd_ideas(platform, queue, args, client=None):
    _generate(platform, queue, args.count, args.theme, not args.no_web, client)


def cmd_list(platform, queue, args):
    items = queue.items if args.status == "all" else queue.with_status(*([args.status] if args.status else WAITING))
    if not items:
        print(f"Nothing here. Try: python -m {platform.name}_agent ideas")
    for item in items:
        flags = " [fact-check]" if item.get("fact_check") else ""
        print(f"#{item['id']:<4} {item['status']:<9} {item['hook']}{flags}")


def cmd_show(platform, queue, args):
    _print_item(platform, queue.get(args.id))


def cmd_revise(platform, queue, args):
    item = _unrendered(queue, args.id)
    item.update(plans.revise(platform, platform.profile, item, args.feedback), status="draft")
    item.pop("clips", None)  # a stock video gets fresh clips for the new plan
    _print_item(platform, item)


def cmd_set_status(platform, queue, args):
    for item_id in args.ids:
        item = _unrendered(queue, item_id) if args.status == "approved" else queue.get(item_id)
        queue.set_status(item_id, args.status)
        print(f"#{item_id} {args.status}")
        for problem in plans.problems(platform, item):
            print(f"  ! {problem}")


def cmd_make(platform, queue, args, hf=None, client=None, assemble=None, pexels=None, pictures=None):
    item = queue.get(args.id)
    if item["status"] not in ("approved", "rendered", "failed"):
        raise SystemExit(f"#{item['id']} is {item['status']}; approve it first.")
    if is_upload(item):  # your own clips, made from the prompts on the card
        files = render.uploaded(upload_folder(platform, item["id"]), len(item["shots"]))
        missing = [n for n, f in enumerate(files, 1) if f is None]
        if missing:
            item["error"] = f"Add your clip for shot {', '.join(map(str, missing))} first (Add clip on the card)."
            logging.error("#%s: %s", item["id"], item["error"])
            return 1
        item["clips"] = [{"video_url": str(f.resolve()), "source": f"upload:{f.name}"} for f in files]
        queue.set_status(item["id"], "rendered", error="")
    try:
        if getattr(args, "new_clips", False) and is_free(item):  # free: find or draw different visuals
            old = {c["source"] for c in item.pop("clips", []) if c.get("source")}
        else:
            old = set()
        if not item.get("clips"):  # never pay for the same render twice
            if is_stock(item):  # free stock clips, none already used in another video
                exclude = render.used_clips(queue.items, except_id=item["id"]) | old
                item["clips"] = render.render_stock(item, platform.seconds, pexels, exclude)
            elif is_pictures(item):  # free AI pictures, brought to life
                folder = Path("build") / platform.name / str(item["id"]) / "pictures"
                item["clips"] = images.render_pictures(item, platform.seconds, folder, pictures)
            else:  # an AI plan: Higgsfield
                item["clips"] = render.render(item, platform.seconds, hf)
            queue.set_status(item["id"], "rendered", error="")
            queue.save()
        options = {}
        if platform.burn_text:
            # Your own tracks in assets/music first; otherwise a tune made for this video. "none": silent.
            setting = platform.setting("MUSIC", "assets/music")
            music = "none" if setting.lower() == "none" else render.pick_music(setting, item["id"])
            texts = [s["on_screen_text"] for s in item["shots"]]
            options = dict(texts=texts, seconds=platform.seconds, audio=True, music=music, seed=item["id"])
        video = (assemble or render.assemble)(item["clips"], Path("build") / platform.name / str(item["id"]), **options)
        if getattr(args, "no_upload", False):
            print(f"Rendered #{item['id']}: {video}")
            return 0
        fields = platform.publish(client or platform.client(), video, item)
    except (render.RenderError, *platform.errors) as e:
        queue.set_status(item["id"], "failed", error=str(e))
        logging.error("#%s failed: %s", item["id"], e)
        return 1
    status = fields.pop("status", platform.published_status)
    queue.set_status(item["id"], status, error="", **fields)
    print(platform.done(item))
    return 0


def cmd_autopilot(platform, queue, args, claude=None, hf=None, client=None, assemble=None, pexels=None):
    auto = platform.setting("AUTO_APPROVE", "").lower() == "true"
    # Unattended, only approved plans count: plans held for a fact-check must not stop the daily video.
    waiting = len(queue.with_status("approved", "rendered") if auto else queue.with_status("draft", "approved", "rendered"))
    generation_failed = False
    if waiting < args.min_drafts and claude is None and not llm.available():
        logging.info("No AI reachable here (%s); only making what is already approved.", llm.provider())
    elif waiting < args.min_drafts:
        logging.info("%d plans waiting (minimum %d); planning %d more", waiting, args.min_drafts, args.count)
        try:
            _generate(platform, queue, args.count, "", True, claude, unattended=auto)
        except Exception as e:  # still make what is already approved; the run ends red below
            logging.error("Planning failed: %s", e)
            generation_failed = True
    if auto:
        for item in queue.with_status("draft"):
            # Only plans with nothing to verify are made without a human look.
            if not item.get("fact_check") and not plans.problems(platform, item):
                queue.set_status(item["id"], "approved", approved_by="autopilot")
    # Plans made from your own clips wait until you have added them in the office.
    def ready(i):
        return not is_upload(i) or has_clips(platform, i)

    rendered = [i for i in queue.with_status("rendered") if ready(i)]
    approved = [i for i in queue.with_status("approved") if ready(i)]
    item = rendered[0] if rendered else min(approved, key=lambda i: (i.get("approved_at", ""), i["id"]), default=None)
    if item is None:
        logging.info("No approved plans waiting.")
        return int(generation_failed)
    made = cmd_make(platform, queue, argparse.Namespace(id=item["id"]), hf, client, assemble, pexels)
    return made or int(generation_failed)


def _generate(platform, queue, count, theme, use_web, client=None, unattended=False):
    profile = platform.profile
    new = plans.generate(platform, profile, count, theme, queue.recent_hooks(), use_web, client, unattended,
                         plans.recent_searches(queue.items))
    for plan in new:
        problems = plans.problems(platform, plan)
        if problems:  # one automatic attempt to fix it before it reaches the queue
            plan.update(plans.revise(platform, profile, plan, "Fix this: " + "; ".join(problems), client))
        print()
        _print_item(platform, queue.add(plan))
    print(f"\nAdded {len(new)} plans. Review them, then: python -m {platform.name}_agent approve <id>")


def is_stock(item):
    return "search_query" in item["shots"][0]


def is_pictures(item):
    """A plan drawn as free AI pictures (VIDEO_SOURCE=images)."""
    return "camera" in item["shots"][0]


def is_free(item):
    """Visuals that cost nothing to make again."""
    return is_stock(item) or is_pictures(item)


def is_upload(item):
    """A plan whose clips the owner makes on an AI video website and adds to the office."""
    return "video_prompt" in item["shots"][0]


def upload_folder(platform, item_id):
    return Path("build") / platform.name / str(int(item_id)) / "uploads"


def has_clips(platform, item):
    return all(render.uploaded(upload_folder(platform, item["id"]), len(item["shots"])))


def _unrendered(queue, item_id):
    item = queue.get(item_id)
    if item.get("clips") and not is_free(item):  # paid AI clips are never thrown away
        raise SystemExit(f"#{item_id} is already rendered; plan a new video instead.")
    return item


def _print_item(platform, item):
    print(f"#{item['id']} [{item['status']}] {item.get('pillar', '')}: {item['hook']}")
    for i, shot in enumerate(item["shots"], 1):
        print(f"  Shot {i}: \"{shot['on_screen_text']}\"")
        if "search_query" in shot:
            print(f"    clip:   {shot['search_query']}")
        elif "camera" in shot:
            print(f"    picture: {shot['image_prompt']}")
            print(f"    action:  {shot['action']} ({shot['camera'].replace('_', ' ')})")
        elif "video_prompt" in shot:
            print(f"    prompt: {shot['video_prompt']}")
        else:
            print(f"    image:  {shot['image_prompt']}")
            print(f"    motion: {shot['motion_prompt']}")
    print(f"  Voiceover: {item['voiceover']}")
    print(f"  Caption: {item['caption']}")
    for problem in plans.problems(platform, item):
        print(f"  ! {problem}")
    if item.get("sources"):
        print("  Sources: " + ", ".join(item["sources"]))
    if item.get("fact_check"):
        print(f"  Check before approving: {item['fact_check']}")
    if item.get("url"):
        print(f"  Published: {item['url']}")
    if item.get("error"):
        print(f"  Error: {item['error']}")
