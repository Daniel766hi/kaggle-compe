"""AI content creator for Instagram Reels: Claude plans videos, Higgsfield makes them, Reels go live.

    python -m instagram_agent ideas --count 3       # Claude researches and plans 3 Reels
    python -m instagram_agent list                  # plans waiting
    python -m instagram_agent show 2                # shots, on-screen text, caption, what to fact-check
    python -m instagram_agent revise 2 "shorter on-screen text"
    python -m instagram_agent approve 2             # OK to render AND publish it
    python -m instagram_agent make 2 --no-upload    # render to build/instagram/2/video.mp4 to preview
    python -m instagram_agent make 2                # render (if needed) and publish the Reel
    python -m instagram_agent autopilot             # top up plans, then publish the oldest approved one
    python -m instagram_agent quota                 # Reels published in the last 24 hours
    python -m instagram_agent connect SHORT_TOKEN   # one-time setup, see README

Instagram's API has no drafts: an approved plan is published as soon as it is made, with its
on-screen text burned in and music from assets/music/ (or silence).

With no arguments the command is read from INSTAGRAM_AGENT_COMMAND (used by the GitHub Actions workflow).
"""

import os
import re
import sys

from shorts import cli, render

from . import instagram

AI_DISCLOSURE = "Visuals made with AI."
FINISH = (
    "The owner reviews every plan. The video is then published to Instagram Reels exactly as rendered: "
    "each shot's on-screen text is burned into the video and the only other words are the caption, "
    "so the on-screen text must tell the story on its own. Keep it to {words} words per shot or fewer, "
    "plain text without emoji. The voiceover is a script the owner may record later."
)
SCREEN_WORDS = 12


def caption_with_disclosure(caption):
    """Say the visuals are AI-made, as Meta asks for realistic AI content, unless the caption already does."""
    return caption if re.search(r"\bai\b", caption, re.IGNORECASE) else f"{caption}\n\n{AI_DISCLOSURE}"


def final_caption(item):
    """Stock clips: credit their creators. AI clips: say the visuals are AI-made."""
    credit = render.credits(item.get("clips", []))
    return f"{item['caption']}\n\n{credit}" if credit else caption_with_disclosure(item["caption"])


def _publish(client, video, item):
    info = render.probe(video)  # check Instagram's Reels requirements before spending an upload
    if not 3 <= info["duration"] <= 15 * 60:
        raise instagram.InstagramError(f"video is {info['duration']:.1f} s; Reels must be 3 s to 15 min")
    if info["streams"].get("audio", {}).get("codec_name") != "aac":
        raise instagram.InstagramError("video needs an AAC audio track")
    return client.publish_reel(video, final_caption(item))


def _done(item):
    return f"#{item['id']} is live on Instagram: {item.get('url') or '(link not returned)'}"


def _extra_commands(sub):
    p = sub.add_parser("quota", help="Reels published through the API in the last 24 hours")
    p.set_defaults(run=lambda platform, queue, args: print(instagram.InstagramClient.from_env().quota()))

    p = sub.add_parser("connect", help="turn a Graph API Explorer token into INSTAGRAM_USER_ID and a lasting token")
    p.add_argument("short_token", help="user token from developers.facebook.com/tools/explorer")
    p.set_defaults(run=cmd_connect)


def cmd_connect(platform, queue, args):
    missing = [k for k in ("META_APP_ID", "META_APP_SECRET") if not os.environ.get(k)]
    if missing:
        raise SystemExit(f"Set {', '.join(missing)} (developers.facebook.com -> your app -> App settings -> Basic).")
    accounts = instagram.connect(os.environ["META_APP_ID"], os.environ["META_APP_SECRET"], args.short_token)
    if not accounts:
        raise SystemExit(
            "No Instagram professional account found. Switch the account to Creator or Business, link it to a "
            "Facebook Page, and grant the token instagram_basic, instagram_content_publish, pages_show_list "
            "and pages_read_engagement."
        )
    for account in accounts:
        print(f"\n@{account['username']} (Page: {account['page']}). Save these as GitHub secrets:")
        print(f"INSTAGRAM_USER_ID={account['user_id']}")
        print(f"INSTAGRAM_ACCESS_TOKEN={account['access_token']}")


PLATFORM = cli.Platform(
    name="instagram",
    title="Instagram Reels",
    env="INSTAGRAM",
    finish=FINISH.format(words=SCREEN_WORDS),
    published_status="posted",
    publish=_publish,
    client=instagram.InstagramClient.from_env,
    errors=(instagram.InstagramError,),
    done=_done,
    burn_text=True,
    screen_words=SCREEN_WORDS,
    extra_commands=_extra_commands,
)


def main(argv=None):
    return cli.main(PLATFORM, __doc__, argv)


if __name__ == "__main__":
    sys.exit(main())
