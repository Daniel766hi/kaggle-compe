"""The office's local web server: the page, a small JSON API and the background check-ins.

It only listens on 127.0.0.1. Every request that changes something must carry the X-Office
header and come to a localhost Host name, so another website open in your browser can't press
the office's buttons for you.
"""

import json
import logging
import mimetypes
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from . import desks

STATIC = Path(__file__).with_name("static")
LOCAL_HOSTS = {"127.0.0.1", "localhost"}
ACTIONS = {
    "approve": "approving",
    "reject": "rejecting",
    "post": "posting to X",
    "render": "rendering the video",
    "publish": "publishing",
    "new_clips": "finding new clips",
}
X_INTENT = "https://x.com/intent/post?text="  # opens X's composer with the text filled in (free)


class OfficeApp:
    """Everything the HTTP handler needs, so it can be tested without a socket."""

    def __init__(self, office, git=None):
        self.office = office
        self.desks = {a.desk.key: (k, a.desk) for k, a in office.team.items() if a.desk is not None}
        self.jobs = {}  # "tiktok:3" -> what's happening to it
        self.git = git or _git
        self.syncing = False

    def state(self):
        agents = []
        for key, agent in self.office.team.items():
            thread = self.office.threads[key]
            needs = 0
            if agent.desk is not None:
                needs = sum(len(thread.attention.get(s, [])) for s in ("draft", "failed", "rendered"))
            agents.append({
                "key": key, "name": agent.name, "role": agent.role, "emoji": agent.emoji, "color": agent.color,
                "status": self.office.status[key], "unread": thread.unread(), "needs": needs,
                "desk": agent.desk.key if agent.desk is not None else None,
                "last": thread.feed[-1] if thread.feed else None,
            })  # fmt: skip
        return {"agents": agents, "jobs": self.jobs, "syncing": self.syncing}

    def feed(self, key, after=0):
        return [e for e in self.office.threads[key].feed if e["id"] > after]

    def mark_read(self, key, upto):
        thread = self.office.threads[key]
        thread.read_upto = max(thread.read_upto, int(upto))
        thread.save()

    def chat(self, key, text):
        if key not in self.office.team or not text.strip():
            raise ValueError("unknown agent or empty message")
        if self.office.locks[key].locked():
            raise ValueError(f"{self.office.team[key].name} is still busy with your last message")
        threading.Thread(target=self.office.say, args=(key, text.strip()), daemon=True).start()

    def item(self, desk_key, item_id):
        _, desk = self.desks[desk_key]
        item = desk.item(item_id)
        out = desks.summary(desk, item, full=True)
        out["desk"] = desk_key
        out["job"] = self.jobs.get(f"{desk_key}:{item_id}", "")
        out["actions"] = self._actions(desk_key, item)
        if "share" in out["actions"]:
            out["share_urls"] = [X_INTENT + quote(post) for post in item["posts"]]
        if desk_key != "x" and desk.video_path(item_id).exists():
            out["video"] = f"/media/{desk_key}/{int(item_id)}.mp4"
        return out

    def action(self, desk_key, item_id, action):
        agent_key, desk = self.desks[desk_key]
        item = desk.item(item_id)
        if action not in self._actions(desk_key, item) or action == "share":
            raise ValueError(f"can't {action} #{item_id} while it is {item['status']}")
        if action in ("approve", "reject", "mark_posted"):
            getattr(desk, action)(item_id)
            return
        job = f"{desk_key}:{item_id}"
        if job in self.jobs:
            raise ValueError(f"#{item_id} is already being worked on")
        self.jobs[job] = ACTIONS[action]
        threading.Thread(target=self._run_job, args=(agent_key, desk, item_id, action, job), daemon=True).start()

    def _run_job(self, agent_key, desk, item_id, action, job):
        tag = f"[[{desk.key}:{item_id}]]"
        try:
            if action == "post":
                item = desk.publish(item_id)
                self.office.notify(agent_key, f"Posted! {tag} {item.get('url', '')}")
            elif action == "render":
                desk.render(item_id)
                self.office.notify(agent_key, f"Your video is rendered. Have a look before it goes out: {tag}")
            elif action == "new_clips":
                desk.new_clips(item_id)
                self.office.notify(agent_key, f"New clips are in. Have another look: {tag}")
            else:
                item = desk.publish(item_id)
                where = "is in your TikTok inbox. Add a sound in the app and post it" if item["status"] == "sent" else "is live"
                self.office.notify(agent_key, f"Done: {tag} {where}. {item.get('url', '')}".strip())
        except Exception as e:
            logging.exception("%s failed", job)
            self.office.notify(agent_key, f"That didn't work for {tag}: {e}")
        finally:
            self.jobs.pop(job, None)
            self.office.checkin()

    def sync(self):
        """Pull the queues the scheduled runs changed, then push yours (content/ only)."""
        if self.syncing:
            raise ValueError("already syncing")
        self.syncing = True

        def run():
            try:
                self.office.notify("maya", self.git())
            except Exception as e:
                self.office.notify("maya", f"Sync with GitHub failed: {e}")
            finally:
                self.syncing = False
                self.office.checkin()

        threading.Thread(target=run, daemon=True).start()

    def _actions(self, desk_key, item):
        actions = _actions(desk_key, item)
        if desk_key == "x" and "post" in actions and not self.desks["x"][1].api_ready():
            actions = ["share", "mark_posted", "reject"]  # no paid X API: post it yourself
        return actions

    def media(self, desk_key, item_id):
        _, desk = self.desks[desk_key]
        return desk.video_path(item_id)


def _actions(desk_key, item):
    """The buttons an item's card shows."""
    status = item["status"]
    if desk_key == "x":
        if status in ("draft", "failed") and not item.get("tweet_ids"):  # never re-post a partly posted thread
            return ["approve", "reject"]
        return ["post", "reject"] if status == "approved" else []
    if status == "approved":
        return ["render", "publish", "reject"]
    if status in ("rendered", "failed") and item.get("clips"):  # rendered: publish without paying again
        stock = "search_query" in item["shots"][0]
        return ["publish", "new_clips", "reject"] if stock else ["publish", "reject"]
    return ["approve", "reject"] if status in ("draft", "failed") else []


def _git():
    def run(*args):
        result = subprocess.run(["git", *args], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        return result.stdout

    run("add", "content")
    changed = run("diff", "--cached", "--name-only").split()
    if changed:
        run("commit", "-m", "Office: update content queues", "--", "content")  # nothing else you staged
    run("pull", "--rebase", "--autostash")
    if changed:
        run("push")
    pushed = f"pushed your changes to {len(changed)} queue file(s)" if changed else "nothing of yours to push"
    return f"Synced with GitHub: pulled the latest from the scheduled runs, {pushed}."


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            logging.debug(fmt, *args)

        def _send(self, code, body, content_type="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _local(self):
            return (self.headers.get("Host") or "").rsplit(":", 1)[0] in LOCAL_HOSTS

        def do_GET(self):
            if not self._local():
                return self._send(403, {"error": "local requests only"})
            url = urlparse(self.path)
            parts = [p for p in url.path.split("/") if p]
            try:
                if not parts:
                    return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
                if parts == ["api", "state"]:
                    return self._send(200, app.state())
                if parts[:2] == ["api", "feed"] and len(parts) == 3:
                    after = int(parse_qs(url.query).get("after", ["0"])[0])
                    return self._send(200, app.feed(parts[2], after))
                if parts[:2] == ["api", "item"] and len(parts) == 4:
                    return self._send(200, app.item(parts[2], int(parts[3])))
                if parts[0] == "media" and len(parts) == 3 and parts[2].endswith(".mp4"):
                    path = app.media(parts[1], int(parts[2][:-4]))
                    if path.exists():
                        return self._send(200, path.read_bytes(), mimetypes.guess_type(path.name)[0] or "video/mp4")
                return self._send(404, {"error": "not found"})
            except (KeyError, ValueError) as e:
                return self._send(404, {"error": str(e)})

        def do_POST(self):
            if not self._local() or self.headers.get("X-Office") != "1":
                return self._send(403, {"error": "local office requests only"})
            parts = [p for p in urlparse(self.path).path.split("/") if p]
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            try:
                if parts[:2] == ["api", "chat"] and len(parts) == 3:
                    app.chat(parts[2], body.get("text", ""))
                elif parts[:2] == ["api", "read"] and len(parts) == 3:
                    app.mark_read(parts[2], body.get("upto", 0))
                elif parts[:2] == ["api", "action"] and len(parts) == 4:
                    app.action(parts[2], int(parts[3]), body.get("action", ""))
                elif parts == ["api", "checkin"]:
                    app.office.checkin()
                elif parts == ["api", "sync"]:
                    app.sync()
                else:
                    return self._send(404, {"error": "not found"})
                return self._send(200, {"ok": True})
            except (KeyError, ValueError) as e:
                return self._send(400, {"error": str(e)})

    return Handler


def serve(app, port=8765, checkin_minutes=30):
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(app))

    def checkins():
        while True:
            try:
                app.office.checkin()
            except Exception:
                logging.exception("check-in failed")
            stop.wait(checkin_minutes * 60)

    stop = threading.Event()
    threading.Thread(target=checkins, daemon=True).start()
    return server
