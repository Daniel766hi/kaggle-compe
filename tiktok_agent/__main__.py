"""AI content creator for TikTok: Claude plans videos, Higgsfield makes them, TikTok gets a draft.

    python -m tiktok_agent ideas --count 3          # Claude researches and plans 3 videos
    python -m tiktok_agent list                     # plans waiting
    python -m tiktok_agent show 2                   # shots, voiceover, caption, what to fact-check
    python -m tiktok_agent revise 2 "make the hook about the rupiah record"
    python -m tiktok_agent approve 2                # OK to spend Higgsfield credits on it
    python -m tiktok_agent make 2 --no-upload       # render to build/tiktok/2/video.mp4 to preview
    python -m tiktok_agent make 2                   # render (if needed) and send to your TikTok inbox
    python -m tiktok_agent status 2                 # where the upload is on TikTok's side
    python -m tiktok_agent autopilot                # top up plans, then make the oldest approved one
    python -m tiktok_agent auth-url --redirect-uri https://...   # one-time TikTok login
    python -m tiktok_agent auth-code CODE --redirect-uri https://...

With no arguments the command is read from TIKTOK_AGENT_COMMAND (used by the GitHub Actions workflow).
"""

import argparse
import logging
import os
import shlex
import sys
from pathlib import Path

from x_agent.brain import load_profile

from . import concepts, render, tiktok
from .concepts import VideoQueue

WAITING = ("draft", "approved", "rendered", "failed")
BUILD_DIR = Path("build/tiktok")


def settings():
    """Shots per video and seconds per shot: 3 x 5 s by default (Higgsfield bills video per second)."""
    return int(os.environ.get("TIKTOK_SHOTS") or 3), int(os.environ.get("TIKTOK_CLIP_SECONDS") or 5)


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:] or shlex.split(os.environ.get("TIKTOK_AGENT_COMMAND") or "list")
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    queue = VideoQueue(args.queue)
    try:
        return args.run(queue, args) or 0
    finally:
        queue.save()  # keep rendered clips and upload ids even if a later step failed


def _parser():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--queue", help="queue file (default: $TIKTOK_QUEUE or content/tiktok_queue.json)")
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

    p = sub.add_parser("make", help="render an approved plan and send it to your TikTok inbox")
    p.add_argument("id", type=int)
    p.add_argument("--no-upload", action="store_true", help="only render, to preview the mp4")
    p.set_defaults(run=cmd_make)

    p = sub.add_parser("status", help="check an upload on TikTok")
    p.add_argument("id", type=int)
    p.set_defaults(run=cmd_status)

    p = sub.add_parser("autopilot", help="top up plans, then make the oldest approved one")
    p.add_argument("--min-drafts", type=int, default=int(os.environ.get("TIKTOK_MIN_DRAFTS") or 3))
    p.add_argument("--count", type=int, default=3, help="plans to generate when topping up")
    p.set_defaults(run=cmd_autopilot)

    p = sub.add_parser("auth-url", help="print the TikTok login link (one-time setup)")
    p.add_argument("--redirect-uri", required=True, help="a redirect URI registered on your TikTok app")
    p.set_defaults(run=lambda queue, args: print(tiktok.authorize_url(args.redirect_uri)))

    p = sub.add_parser("auth-code", help="exchange the code from the redirect for tokens")
    p.add_argument("code")
    p.add_argument("--redirect-uri", required=True)
    p.set_defaults(run=cmd_auth_code)
    return parser


def cmd_ideas(queue, args, client=None):
    _generate(queue, args.count, args.theme, not args.no_web, client)


def cmd_list(queue, args):
    items = queue.items if args.status == "all" else queue.with_status(*([args.status] if args.status else WAITING))
    if not items:
        print("Nothing here. Try: python -m tiktok_agent ideas")
    for item in items:
        flags = " [fact-check]" if item.get("fact_check") else ""
        print(f"#{item['id']:<4} {item['status']:<9} {item['hook']}{flags}")


def cmd_show(queue, args):
    _print_item(queue.get(args.id))


def cmd_revise(queue, args):
    item = _unrendered(queue, args.id)
    item.update(concepts.revise(load_profile(), item, args.feedback, *settings()), status="draft")
    _print_item(item)


def cmd_set_status(queue, args):
    for item_id in args.ids:
        item = _unrendered(queue, item_id) if args.status == "approved" else queue.get(item_id)
        queue.set_status(item_id, args.status)
        print(f"#{item_id} {args.status}")
        for problem in concepts.problems(item, *settings()):
            print(f"  ! {problem}")


def cmd_make(queue, args, hf=None, uploader=None, assemble=None):
    item = queue.get(args.id)
    if item["status"] not in ("approved", "rendered", "failed"):
        raise SystemExit(f"#{item['id']} is {item['status']}; approve it first.")
    try:
        if not item.get("clips"):  # never pay for the same render twice
            item["clips"] = render.render(item, settings()[1], hf)
            queue.set_status(item["id"], "rendered", error="")
            queue.save()
        video = (assemble or render.assemble)(item["clips"], BUILD_DIR / str(item["id"]))
        if getattr(args, "no_upload", False):
            print(f"Rendered #{item['id']}: {video}")
            return 0
        client = uploader or tiktok.TikTokClient.from_env()
        publish_id = client.upload_draft(video)
    except (render.RenderError, tiktok.TikTokError) as e:
        queue.set_status(item["id"], "failed", error=str(e))
        logging.error("#%s failed: %s", item["id"], e)
        return 1
    queue.set_status(item["id"], "sent", publish_id=publish_id, error="")
    print(f"#{item['id']} is in your TikTok inbox. Open TikTok, add sound and text, turn on the")
    print("AI-generated content label, paste the caption and post:\n")
    print(item["caption"])
    return 0


def cmd_status(queue, args):
    item = queue.get(args.id)
    if not item.get("publish_id"):
        raise SystemExit(f"#{item['id']} hasn't been uploaded yet.")
    print(tiktok.TikTokClient.from_env().status(item["publish_id"]))


def cmd_autopilot(queue, args, claude=None, hf=None, uploader=None, assemble=None):
    waiting = len(queue.with_status("draft", "approved", "rendered"))
    if waiting < args.min_drafts:
        logging.info("%d plans waiting (minimum %d); planning %d more", waiting, args.min_drafts, args.count)
        _generate(queue, args.count, "", True, claude)
    if os.environ.get("TIKTOK_AUTO_APPROVE", "").lower() == "true":
        for item in queue.with_status("draft"):
            # Only plans with nothing to verify are rendered without a human look.
            if not item.get("fact_check") and not concepts.problems(item, *settings()):
                queue.set_status(item["id"], "approved", approved_by="autopilot")
    item = (queue.with_status("rendered") or [None])[0] or queue.next_approved()
    if item is None:
        logging.info("No approved plans waiting.")
        return 0
    return cmd_make(queue, argparse.Namespace(id=item["id"]), hf, uploader, assemble)


def cmd_auth_code(queue, args):
    tokens = tiktok.exchange_code(args.code, args.redirect_uri)
    print("Logged in. Save these as GitHub secrets (and locally as environment variables):")
    print(f"TIKTOK_REFRESH_TOKEN={tokens['refresh_token']}")
    print(f"(valid for {int(tokens.get('refresh_expires_in', 0)) // 86400} days; access tokens are refreshed each run)")


def _generate(queue, count, theme, use_web, client=None):
    profile, (shots, seconds) = load_profile(), settings()
    plans = concepts.generate(profile, count, shots, seconds, theme, queue.recent_hooks(), use_web, client)
    for plan in plans:
        problems = concepts.problems(plan, shots, seconds)
        if problems:  # one automatic attempt to fix it before it reaches the queue
            plan.update(concepts.revise(profile, plan, "Fix this: " + "; ".join(problems), shots, seconds, client))
        print()
        _print_item(queue.add(plan))
    print(f"\nAdded {len(plans)} plans. Review them, then: python -m tiktok_agent approve <id>")


def _unrendered(queue, item_id):
    item = queue.get(item_id)
    if item.get("clips"):
        raise SystemExit(f"#{item_id} is already rendered; plan a new video instead.")
    return item


def _print_item(item):
    print(f"#{item['id']} [{item['status']}] {item.get('pillar', '')}: {item['hook']}")
    for i, shot in enumerate(item["shots"], 1):
        print(f"  Shot {i}: \"{shot['on_screen_text']}\"")
        print(f"    image:  {shot['image_prompt']}")
        print(f"    motion: {shot['motion_prompt']}")
    print(f"  Voiceover: {item['voiceover']}")
    print(f"  Caption: {item['caption']}")
    for problem in concepts.problems(item, *settings()):
        print(f"  ! {problem}")
    if item.get("sources"):
        print("  Sources: " + ", ".join(item["sources"]))
    if item.get("fact_check"):
        print(f"  Check before approving: {item['fact_check']}")
    if item.get("error"):
        print(f"  Error: {item['error']}")


if __name__ == "__main__":
    sys.exit(main())
