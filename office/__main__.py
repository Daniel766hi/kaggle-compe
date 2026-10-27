"""Open the AI Office: chat with your content team in the browser.

    python -m office                 # http://127.0.0.1:8765
    python -m office --phone         # also open it on a phone on the same Wi-Fi (QR code)
    python -m office --anywhere      # open it on your phone from anywhere (free Cloudflare tunnel)
    python -m office --port 9000 --checkin-minutes 15 --no-browser

Free by default: the agents think with Gemini (a free GEMINI_API_KEY) or a local model through
Ollama (see llm.py); videos are free AI pictures (Cloudflare, see shorts/images.py) or free stock
clips (PIXABAY_API_KEY); X posts open in X for you to post. Set ANTHROPIC_API_KEY to use Claude
instead, and X_* keys to post to X from the office (X charges per post).
"""

import argparse
import logging
import os
import webbrowser

import llm
import local_env
from instagram_agent.__main__ import PLATFORM as INSTAGRAM
from shorts import images
from tiktok_agent.__main__ import PLATFORM as TIKTOK

from . import phone
from .chat import Office
from .desks import VideoDesk, XDesk
from .server import OfficeApp, serve
from .team import build_team


def main(argv=None):
    local_env.load()  # keys saved by the setup script, when run on your computer
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--checkin-minutes", type=int, default=30, help="how often the team checks for things that need you")
    parser.add_argument("--data-dir", default="office_data", help="where conversations are kept (not committed)")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--phone", action="store_true", help="also open the office to phones on your Wi-Fi (asks for a password)")
    parser.add_argument("--anywhere", action="store_true", help="open it on your phone from anywhere, through a free Cloudflare tunnel")
    args = parser.parse_args(argv)
    mode = (os.environ.get("OFFICE_PHONE") or "").strip().lower()  # saved by the setup script
    args.phone = args.phone or mode in ("wifi", "anywhere")
    args.anywhere = args.anywhere or mode == "anywhere"
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    team = build_team(XDesk(), VideoDesk(TIKTOK), VideoDesk(INSTAGRAM))
    app = OfficeApp(Office(team, args.data_dir))
    in_codespace = os.environ.get("CODESPACES") == "true"  # GitHub logs you in to forwarded ports
    host = "0.0.0.0" if args.phone else "127.0.0.1"
    if args.phone or args.anywhere:
        app.password = phone.password()
    elif in_codespace:  # reached through GitHub's port forwarding, which only lets you in
        app.password = os.environ.get("OFFICE_PASSWORD") or None
        app.any_host = True
    server = serve(app, args.port, args.checkin_minutes, host)
    url = f"http://127.0.0.1:{args.port}"
    print(f"AI Office is open at {url}  (Ctrl+C to close)")
    _report_setup()

    tunnel = None
    key = phone.login_key(app.password) if app.password else ""
    if args.phone:
        address = phone.lan_address()
        if address:
            app.links.append({"label": "Phone on the same Wi-Fi", "url": f"http://{address}:{args.port}/?key={key}"})
    if args.anywhere:
        try:
            tunnel, public = phone.start_tunnel(args.port)
            app.links.append({"label": "Phone, anywhere", "url": f"{public}/?key={key}"})
        except RuntimeError as e:
            print(e)
    for link in app.links:
        print(f"\n{link['label']}: scan this with your phone's camera, or open {link['url']}")
        phone.print_qr(link["url"])
    if app.password and (args.phone or args.anywhere):
        print(f"\nOffice password (if your phone asks): {app.password}")
        if args.phone:
            print("If Windows asks whether Python may use the network, allow it on private networks.")
    if in_codespace:
        print("In a Codespace: open the Ports tab and click the address of port", args.port, "(keep it Private).")

    if not args.no_browser and not in_codespace:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if tunnel:
            tunnel.terminate()


def _report_setup():
    if llm.available():
        print(f"The team thinks with {llm.describe()}.")
    elif llm.provider() == "ollama":
        print("No AI yet. The easiest: a free Gemini key from https://aistudio.google.com/apikey,")
        print("then run: python -m local_env set GEMINI_API_KEY <your key>  and open the office again.")
        print(f"(Or install Ollama from https://ollama.com and run `ollama pull {llm.ollama_model()}`.)")
    if images.configured():
        print("Videos are drawn as free AI pictures (Cloudflare Workers AI).")
    elif not (os.environ.get("PIXABAY_API_KEY") or os.environ.get("PEXELS_API_KEY")):
        print("No picture or stock-clip key yet: video agents can plan, but rendering needs one (run the setup script).")


if __name__ == "__main__":
    main()
