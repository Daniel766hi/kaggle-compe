"""AI agent for an X (Twitter) account: ideas, drafts, review queue and posting.

    python -m x_agent ideas --count 5             # Claude researches and drafts 5 posts into the queue
    python -m x_agent ideas --theme "haze season" # ideas on one theme
    python -m x_agent list                        # drafts and approved posts waiting
    python -m x_agent show 3                      # full text, sources and what to fact-check
    python -m x_agent revise 3 "shorter, lead with the number"
    python -m x_agent edit 3 --text "my own wording"   # repeat --text for a thread
    python -m x_agent approve 3 4                 # ready to publish
    python -m x_agent reject 5
    python -m x_agent post [--dry-run]            # publish the oldest approved post
    python -m x_agent autopilot                   # top up drafts if few are waiting, then post one

With no arguments the command is read from X_AGENT_COMMAND (used by the GitHub Actions workflow).
"""

import argparse
import logging
import os
import shlex
import sys

import llm
import local_env

from . import brain, text
from .queue import PostQueue
from .x_client import XClient, XError, post_url

WAITING = ("draft", "approved", "failed")


def main(argv=None):
    local_env.load()  # keys saved by the setup script, when run on your computer
    if argv is None:
        argv = sys.argv[1:] or shlex.split(os.environ.get("X_AGENT_COMMAND") or "list")
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    queue = PostQueue(args.queue)
    try:
        return args.run(queue, args) or 0
    finally:
        queue.save()  # keep whatever was drafted or posted, even if a later step failed


def _parser():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--queue", help="queue file (default: $X_QUEUE or content/x_queue.json)")
    sub = parser.add_subparsers(required=True, metavar="command")

    p = sub.add_parser("ideas", help="research and draft new posts into the queue")
    p.add_argument("--count", type=int, default=5)
    p.add_argument("--theme", default="", help="topic to focus on (default: mix of content pillars)")
    p.add_argument("--no-web", action="store_true", help="don't search the web")
    p.set_defaults(run=cmd_ideas)

    p = sub.add_parser("list", help="show queue items")
    p.add_argument("--status", choices=["draft", "approved", "posted", "rejected", "failed", "all"])
    p.set_defaults(run=cmd_list)

    p = sub.add_parser("show", help="show one item in full")
    p.add_argument("id", type=int)
    p.set_defaults(run=cmd_show)

    p = sub.add_parser("revise", help="have Claude rewrite a draft with your feedback")
    p.add_argument("id", type=int)
    p.add_argument("feedback")
    p.set_defaults(run=cmd_revise)

    p = sub.add_parser("edit", help="replace a draft's text with your own")
    p.add_argument("id", type=int)
    p.add_argument("--text", action="append", required=True, help="post text; repeat for a thread")
    p.set_defaults(run=cmd_edit)

    for name, status in (("approve", "approved"), ("reject", "rejected")):
        p = sub.add_parser(name, help=f"mark items {status}")
        p.add_argument("ids", type=int, nargs="+")
        p.set_defaults(run=cmd_set_status, status=status)

    p = sub.add_parser("post", help="publish the oldest approved item")
    p.add_argument("--dry-run", action="store_true", help="print what would be posted")
    p.set_defaults(run=cmd_post)

    p = sub.add_parser("autopilot", help="top up drafts, then publish one approved item")
    p.add_argument("--min-drafts", type=int, default=int(os.environ.get("X_MIN_DRAFTS") or 5))
    p.add_argument("--count", type=int, default=5, help="ideas to generate when topping up")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(run=cmd_autopilot)
    return parser


def cmd_ideas(queue, args):
    return _generate(queue, args.count, args.theme, not args.no_web)


def cmd_list(queue, args):
    items = queue.items if args.status == "all" else queue.with_status(*([args.status] if args.status else WAITING))
    if not items:
        print("Nothing here. Try: python -m x_agent ideas")
    for item in items:
        flags = " [fact-check]" if item.get("fact_check") else ""
        flags += " [too long]" if text.problems(item["posts"]) else ""
        thread = f" ({len(item['posts'])}-post thread)" if len(item["posts"]) > 1 else ""
        print(f"#{item['id']:<4} {item['status']:<9} {item['hook']}{thread}{flags}")


def cmd_show(queue, args):
    _print_item(queue.get(args.id))


def cmd_revise(queue, args):
    item = _unposted(queue, args.id)
    item.update(brain.revise(brain.load_profile(), item, args.feedback), status="draft")
    _print_item(item)


def cmd_edit(queue, args):
    item = _unposted(queue, args.id)
    item.update(posts=args.text, status="draft")
    _print_item(item)


def cmd_set_status(queue, args):
    for item_id in args.ids:
        item = _unposted(queue, item_id)
        problems = text.problems(item["posts"])
        if args.status == "approved" and problems:
            print(f"#{item_id} not approved: {'; '.join(problems)}")
            continue
        queue.set_status(item_id, args.status)
        print(f"#{item_id} {args.status}")


def cmd_post(queue, args, client=None):
    item = queue.next_approved()
    if item is None:
        logging.info("No approved posts waiting.")
        return 0
    problems = text.problems(item["posts"])
    if problems:
        queue.set_status(item["id"], "failed", error="; ".join(problems))
        logging.error("#%s not posted: %s", item["id"], "; ".join(problems))
        return 1
    if args.dry_run:
        print(f"Would post #{item['id']}:")
        _print_item(item)
        return 0
    client = client or XClient.from_env()
    try:
        ids = client.post_thread(item["posts"])
    except XError as e:
        fields = {"error": str(e)}
        if e.posted_ids:  # part of a thread went out; record it so it isn't posted twice
            fields.update(tweet_ids=e.posted_ids, url=post_url(e.posted_ids[0]))
        queue.set_status(item["id"], "failed", **fields)
        logging.error("#%s failed: %s", item["id"], e)
        return 1
    queue.set_status(item["id"], "posted", tweet_ids=ids, url=post_url(ids[0]), error="")
    logging.info("Posted #%s: %s", item["id"], post_url(ids[0]))
    return 0


def cmd_autopilot(queue, args, x_client=None, claude=None):
    auto = os.environ.get("X_AUTO_APPROVE", "").lower() == "true"
    # Unattended, only approved posts count: drafts held for a fact-check must not stop the daily post.
    waiting = len(queue.with_status("approved") if auto else queue.with_status("draft", "approved"))
    generation_failed = False
    if waiting < args.min_drafts and claude is None and not llm.available():
        logging.info("No AI reachable here (%s); only posting what is already approved.", llm.provider())
    elif waiting < args.min_drafts:
        logging.info("%d posts waiting (minimum %d); generating %d ideas", waiting, args.min_drafts, args.count)
        try:
            _generate(queue, args.count, "", True, claude, unattended=auto)
        except Exception as e:  # still publish what is already approved; the run ends red below
            logging.error("Generating ideas failed: %s", e)
            generation_failed = True
    if auto:
        for item in queue.with_status("draft"):
            # Only drafts with nothing to verify are published without a human look.
            if not item.get("fact_check") and not text.problems(item["posts"]):
                queue.set_status(item["id"], "approved", approved_by="autopilot")
    return cmd_post(queue, args, x_client) or int(generation_failed)


def _generate(queue, count, theme, use_web, client=None, unattended=False):
    profile = brain.load_profile()
    ideas = brain.generate_ideas(profile, count, theme, queue.recent_hooks(), use_web, client, unattended)
    for idea in ideas:
        problems = text.problems(idea["posts"])
        if problems:  # one automatic attempt to fix length before it reaches the queue
            idea.update(brain.revise(profile, idea, "Fix this: " + "; ".join(problems), client))
        item = queue.add(idea)
        print()
        _print_item(item)
    print(f"\nAdded {len(ideas)} drafts. Review them, then: python -m x_agent approve <id>")


def _unposted(queue, item_id):
    item = queue.get(item_id)
    if item.get("tweet_ids"):  # posted, or a thread that went out in part
        raise SystemExit(f"#{item_id} is already (partly) on X: {item['url']}. Draft a new idea instead.")
    return item


def _print_item(item):
    print(f"#{item['id']} [{item['status']}] {item.get('pillar', '')}: {item['hook']}")
    for i, post in enumerate(item["posts"], 1):
        label = f"  ({i}/{len(item['posts'])}, {text.weighted_length(post)} chars)"
        print(label + "\n    " + post.replace("\n", "\n    "))
    for problem in text.problems(item["posts"]):
        print(f"  ! {problem}")
    if item.get("sources"):
        print("  Sources: " + ", ".join(item["sources"]))
    if item.get("fact_check"):
        print(f"  Check before approving: {item['fact_check']}")
    if item.get("url"):
        print(f"  Posted: {item['url']}")
    if item.get("error"):
        print(f"  Error: {item['error']}")


if __name__ == "__main__":
    sys.exit(main())
