"""Open the AI Office: chat with your content team in the browser.

    python -m office                 # http://127.0.0.1:8765
    python -m office --port 9000 --checkin-minutes 15 --no-browser

Free by default: the agents think with a local model through Ollama (see llm.py), videos use free
Pexels clips (PEXELS_API_KEY), and X posts open in X for you to post. Set ANTHROPIC_API_KEY to use
Claude instead, and X_* keys to post to X from the office (X charges per post).
"""

import argparse
import logging
import webbrowser

import llm

from instagram_agent.__main__ import PLATFORM as INSTAGRAM
from tiktok_agent.__main__ import PLATFORM as TIKTOK

from .chat import Office
from .desks import VideoDesk, XDesk
from .server import OfficeApp, serve
from .team import build_team


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--checkin-minutes", type=int, default=30, help="how often the team checks for things that need you")
    parser.add_argument("--data-dir", default="office_data", help="where conversations are kept (not committed)")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    team = build_team(XDesk(), VideoDesk(TIKTOK), VideoDesk(INSTAGRAM))
    app = OfficeApp(Office(team, args.data_dir))
    server = serve(app, args.port, args.checkin_minutes)
    url = f"http://127.0.0.1:{args.port}"
    print(f"AI Office is open at {url}  (Ctrl+C to close)")
    if llm.provider() == "claude":
        print("The team thinks with Claude (paid API).")
    elif llm.available():
        print(f"The team thinks with {llm.ollama_model()} on this computer (free).")
    else:
        print(f"Ollama isn't running. Install it from https://ollama.com, run `ollama pull {llm.ollama_model()}`,")
        print("keep the Ollama app open, then refresh the office.")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
