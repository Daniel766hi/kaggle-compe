"""AI content creator for Instagram Reels: the AI plans videos, the office renders them, Reels go live.

    python -m instagram_agent ideas --count 3       # the AI plans 3 Reels
    python -m instagram_agent list                  # plans waiting
    python -m instagram_agent show 2                # shots, on-screen text, caption, what to fact-check
    python -m instagram_agent revise 2 "shorter on-screen text"
    python -m instagram_agent approve 2             # OK to render AND publish it
    python -m instagram_agent make 2 --no-upload    # render to build/instagram/2/video.mp4 to preview
    python -m instagram_agent make 2                # render (if needed) and publish the Reel
    python -m instagram_agent autopilot             # top up plans, then publish the oldest approved one
    python -m instagram_agent quota                 # Reels published in the last 24 hours
    python -m instagram_agent login                 # connect your Instagram account (one time, guided)

Instagram's API has no drafts: an approved plan is published as soon as it is made, with its
on-screen text burned in and music from assets/music/ (or silence).

With no arguments the command is read from INSTAGRAM_AGENT_COMMAND (used by the GitHub Actions workflow).
"""

import os
import re
import sys
import webbrowser

import local_env
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

    p = sub.add_parser("login", help="connect your Instagram account (one-time setup, walks you through it)")
    p.add_argument("short_token", nargs="?", help="a Graph API Explorer token (asked for if left out)")
    p.set_defaults(run=cmd_login)
    p = sub.add_parser("connect", help="the same as login")
    p.add_argument("short_token", nargs="?")
    p.set_defaults(run=cmd_login)


EXPLORER = "https://developers.facebook.com/tools/explorer/"
PERMISSIONS = ("instagram_basic", "instagram_content_publish", "pages_show_list", "pages_read_engagement", "business_management")
STEPS = f"""\
Connect Instagram (one time):
  1. Instagram app -> Settings -> Account type and tools: switch to a Professional account
     (Creator or Business, free), and link it to a Facebook Page (make a Page if you have none:
     facebook.com/pages/create). Instagram -> Settings -> Accounts Center links them.
  2. developers.facebook.com/apps -> Create app -> use case "Manage messaging & content on
     Instagram" (or app type Business). In the app: Instagram -> "API setup with Facebook login".
     App settings -> Basic shows the App ID and App secret.
  3. The Graph API Explorer opens next. Top right: pick your app. Under Permissions, add:
     {', '.join(PERMISSIONS)}
     Click "Generate Access Token", allow everything for your Page and Instagram account, then
     copy the token.
"""


def cmd_login(platform, queue, args, ask=input, open_browser=webbrowser.open):
    print(STEPS)
    for name, label in (("META_APP_ID", "App ID"), ("META_APP_SECRET", "App secret")):
        if not os.environ.get(name):
            value = ask(f"Paste your Meta {label}: ").strip()
            if not value:
                raise SystemExit(f"No {label}; run this again when you have it.")
            local_env.save(name, value)
            os.environ[name] = value
    token = args.short_token
    if not token:
        open_browser(EXPLORER)
        token = ask("Paste the token from the Graph API Explorer: ").strip()
    try:
        accounts = instagram.connect(os.environ["META_APP_ID"], os.environ["META_APP_SECRET"], token)
    except instagram.InstagramError as e:
        raise SystemExit(f"Meta didn't accept that: {e}\nCheck the App ID and secret (App settings -> Basic) and make a new token.") from e
    if not accounts:
        raise SystemExit(
            "No Instagram professional account found on your Pages. Check step 1 (Professional account, linked to a "
            f"Facebook Page), and that the token has {', '.join(PERMISSIONS)} with your Page ticked."
        )
    account = accounts[0]
    if len(accounts) > 1:
        for n, a in enumerate(accounts, 1):
            print(f"  {n}. @{a['username']} (Page: {a['page']})")
        pick = ask("Which account should the office post to? Number: ").strip()
        account = accounts[int(pick) - 1] if pick.isdigit() and 1 <= int(pick) <= len(accounts) else account
    local_env.save("INSTAGRAM_USER_ID", account["user_id"])
    local_env.save("INSTAGRAM_ACCESS_TOKEN", account["access_token"])
    quota = instagram.InstagramClient(account["user_id"], account["access_token"]).quota()
    print(f"\nInstagram is connected: @{account['username']} (Page: {account['page']}), saved in .env.")
    print(f"Reels published through the API in the last 24 hours: {quota['used']} of {quota['total']}.")
    print("Publish in the office now posts Reels there (they go live right away: Instagram has no drafts).")
    print("For the daily GitHub runs too: add INSTAGRAM_USER_ID and INSTAGRAM_ACCESS_TOKEN as repository secrets")
    print("(`python -m local_env get INSTAGRAM_ACCESS_TOKEN` shows the token to copy).")
    return 0


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
