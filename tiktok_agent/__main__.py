"""AI content creator for TikTok: Claude plans videos, Higgsfield makes them, TikTok gets a draft.

    python -m tiktok_agent ideas --count 3          # the AI plans 3 videos
    python -m tiktok_agent list                     # plans waiting
    python -m tiktok_agent show 2                   # shots, voiceover, caption, what to fact-check
    python -m tiktok_agent revise 2 "make the hook about the rupiah record"
    python -m tiktok_agent approve 2                # OK to render it
    python -m tiktok_agent make 2 --no-upload       # render to build/tiktok/2/video.mp4 to preview
    python -m tiktok_agent make 2                   # render (if needed) and send to your TikTok inbox
    python -m tiktok_agent status 2                 # where the upload is on TikTok's side
    python -m tiktok_agent autopilot                # top up plans, then make the oldest approved one
    python -m tiktok_agent login                    # one-time TikTok login (walks you through it)

With no arguments the command is read from TIKTOK_AGENT_COMMAND (used by the GitHub Actions workflow).
"""

import os
import sys

import local_env
from shorts import cli, render

from . import tiktok


def _publish(client, video, item):
    return {"publish_id": client.upload_draft(video)}


def _done(item):
    credit = render.credits(item.get("clips", []))
    if credit:  # stock clips: credit their creators
        return (
            f"#{item['id']} is in your TikTok inbox, with music. Open TikTok (swap in a trending sound if you like),\n"
            f"paste the caption and post:\n\n"
            f"{item['caption']}\n\n{credit}"
        )
    return (
        f"#{item['id']} is in your TikTok inbox, with music. Open TikTok, turn on the AI-generated\n"
        f"content label, paste the caption and post:\n\n{item['caption']}"
    )


def _extra_commands(sub):
    p = sub.add_parser("status", help="check an upload on TikTok")
    p.add_argument("id", type=int)
    p.set_defaults(run=cmd_status)

    p = sub.add_parser("login", help="connect your TikTok account (one-time setup, walks you through it)")
    p.set_defaults(run=cmd_login)

    p = sub.add_parser("auth-url", help="print a login link for a web redirect URI (advanced; use login)")
    p.add_argument("--redirect-uri", required=True, help="a redirect URI registered on your TikTok app")
    p.set_defaults(run=lambda platform, queue, args: print(tiktok.authorize_url(args.redirect_uri)))

    p = sub.add_parser("auth-code", help="exchange the code from the redirect for tokens")
    p.add_argument("code")
    p.add_argument("--redirect-uri", required=True)
    p.set_defaults(run=cmd_auth_code)


def cmd_status(platform, queue, args):
    item = queue.get(args.id)
    if not item.get("publish_id"):
        raise SystemExit(f"#{item['id']} hasn't been uploaded yet.")
    print(tiktok.TikTokClient.from_env().status(item["publish_id"]))


PORTAL_STEPS = f"""\
Connect TikTok (one time). At https://developers.tiktok.com/apps open your app (create one if needed):
  1. App details: under Platforms, tick Desktop (Web isn't needed).
  2. Add products: Login Kit, and Content Posting API (turn on Upload; Direct Post isn't needed).
  3. Login Kit -> Desktop -> Redirect URI: add exactly  {tiktok.DESKTOP_REDIRECT}
  4. Sandbox (top of the page): add your own TikTok account under Target users.
  5. Copy the Client key and Client secret (on the app page, sandbox section).
"""


def cmd_login(platform, queue, args):
    print(PORTAL_STEPS)
    for name, label in (("TIKTOK_CLIENT_KEY", "Client key"), ("TIKTOK_CLIENT_SECRET", "Client secret")):
        if not os.environ.get(name):
            value = input(f"Paste your TikTok {label}: ").strip()
            if not value:
                raise SystemExit(f"No {label}; run this again when you have it.")
            local_env.save(name, value)
            os.environ[name] = value
    tokens = tiktok.login()
    local_env.save("TIKTOK_REFRESH_TOKEN", tokens["refresh_token"])
    days = int(tokens.get("refresh_expires_in", 0)) // 86400
    print(f"TikTok is connected and saved in .env (the login lasts {days} days). Publish now sends videos to your TikTok inbox.")
    print("For the daily GitHub runs too: add TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET and TIKTOK_REFRESH_TOKEN as repository")
    print("secrets. `python -m local_env get TIKTOK_REFRESH_TOKEN` shows the token to copy.")
    return 0


def cmd_auth_code(platform, queue, args):
    tokens = tiktok.exchange_code(args.code, args.redirect_uri)
    print("Logged in. Save these as GitHub secrets (and locally as environment variables):")
    print(f"TIKTOK_REFRESH_TOKEN={tokens['refresh_token']}")
    print(f"(valid for {int(tokens.get('refresh_expires_in', 0)) // 86400} days; access tokens are refreshed each run)")


PLATFORM = cli.Platform(
    name="tiktok",
    title="TikTok",
    env="TIKTOK",
    finish=(
        "The owner reviews every plan. The rendered video, with each shot's on-screen text burned in, "
        "lands in the owner's TikTok inbox with background music, where they post it, so the on-screen text "
        "must tell the story. Keep it to 12 words per shot or fewer, plain text without emoji. The "
        "voiceover is a script the owner may record later."
    ),
    published_status="sent",
    publish=_publish,
    client=tiktok.TikTokClient.from_env,
    errors=(tiktok.TikTokError,),
    done=_done,
    burn_text=True,
    screen_words=12,
    extra_commands=_extra_commands,
)


def main(argv=None):
    return cli.main(PLATFORM, __doc__, argv)


if __name__ == "__main__":
    sys.exit(main())
