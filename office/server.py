"""The office's web server: the page, a small JSON API and the background check-ins.

By default it only listens on 127.0.0.1 and answers only to a localhost Host name. With a password
(`python -m office --phone`, see phone.py) it also listens on your Wi-Fi or behind a tunnel, and
everyone but this computer itself must log in first. Either way, every request that changes
something must carry the X-Office header, so another website open in your browser can't press
the office's buttons for you.
"""

import hmac
import json
import logging
import mimetypes
import shutil
import subprocess
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from shorts import cli as shorts_cli

from . import desks, phone

STATIC = Path(__file__).with_name("static")
LOCAL_HOSTS = {"127.0.0.1", "localhost"}
LOOPBACK = {"127.0.0.1", "::1"}
PROXY_HEADERS = ("Cf-Connecting-Ip", "X-Forwarded-For", "X-Forwarded-Host", "Forwarded")
LOGIN_TRIES_PER_MINUTE = 5
ACTIONS = {
    "approve": "approving",
    "reject": "rejecting",
    "post": "posting to X",
    "render": "rendering the video",
    "publish": "publishing",
    "new_clips": "finding new clips",
}
MAX_UPLOAD = 500 * 1024 * 1024
X_INTENT = "https://x.com/intent/post?text="  # opens X's composer with the text filled in (free)


class OfficeApp:
    """Everything the HTTP handler needs, so it can be tested without a socket."""

    def __init__(self, office, git=None):
        self.office = office
        self.desks = {a.desk.key: (k, a.desk) for k, a in office.team.items() if a.desk is not None}
        self.jobs = {}  # "tiktok:3" -> what's happening to it
        self.git = git or _git
        self.syncing = False
        self.password = None  # set: phones may log in (python -m office --phone)
        self.links = []  # [{"label", "url"}] for opening the office on a phone
        self.any_host = False  # behind GitHub Codespaces' private port forwarding

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
        uploads = desk.uploads(item) if desk_key != "x" else None
        if uploads is not None:
            out["uploads"] = uploads
            if not all(uploads):  # clips still missing: nothing to render yet
                out["actions"] = [a for a in out["actions"] if a not in ("render", "publish")]
        if desk_key != "x" and desk.video_path(item_id).exists():
            out["video"] = f"/media/{desk_key}/{int(item_id)}.mp4"
        if desk_key != "x":
            folder = desk.video_path(item_id).parent / "pictures"
            names = sorted(p.name for p in folder.glob("picture_*.png")) if folder.exists() else []
            if names:
                out["pictures"] = [f"/media/{desk_key}/{int(item_id)}/{n}" for n in names]
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

    def add_clip(self, desk_key, item_id, shot, data, filename):
        agent_key, desk = self.desks[desk_key]
        desk.add_clip(item_id, shot, data, filename)
        item = desk.item(item_id)
        if all(desk.uploads(item)) and item["status"] in ("approved", "rendered", "failed"):
            self.office.notify(agent_key, f"All clips are in for [[{desk_key}:{item_id}]]. Click Render preview to see it.")

    def phone_links(self):
        return {"links": [{**link, "qr": phone.qr_svg(link["url"])} for link in self.links]}

    def picture(self, desk_key, item_id, name):
        """One of the AI pictures a video was drawn from (to post as a photo carousel, say)."""
        _, desk = self.desks[desk_key]
        path = desk.video_path(item_id).parent / "pictures" / Path(name).name
        return path if path.suffix == ".png" and path.exists() else None

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
    if "video_prompt" in item["shots"][0] and status in ("rendered", "failed"):  # your clips: re-render freely
        return ["render", "publish", "reject"]
    if status in ("rendered", "failed") and item.get("clips"):  # rendered: publish without paying again
        free = shorts_cli.is_free(item)  # stock clips or AI pictures: free to swap
        return ["publish", "new_clips", "reject"] if free else ["publish", "reject"]
    return ["approve", "reject"] if status in ("draft", "failed") else []


def _git():
    if not shutil.which("git"):
        raise RuntimeError(
            "Git isn't installed on this computer. Run the setup script again (setup.ps1 or setup.sh): "
            "it installs Git and links this folder to GitHub."
        )

    def run(*args):
        result = subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        return result.stdout

    try:
        run("rev-parse", "--is-inside-work-tree")
    except RuntimeError:
        raise RuntimeError(
            "This folder isn't linked to GitHub (it came from a ZIP). Run the setup script again: "
            "it links the folder and keeps your keys, plans and videos."
        ) from None
    run("add", "content")
    changed = run("diff", "--cached", "--name-only").split()
    if changed:
        run("commit", "-m", "Office: update content queues", "--", "content")  # nothing else you staged
    before = run("rev-parse", "HEAD").strip()
    run("pull", "--rebase", "--autostash")
    updated = [f for f in run("diff", "--name-only", before, "HEAD").split() if not f.startswith("content/")]
    if changed:
        run("push")
    pushed = f"pushed your changes to {len(changed)} queue file(s)" if changed else "nothing of yours to push"
    note = " Updates to the office were downloaded too: close it (Ctrl+C) and open it again to use them." if updated else ""
    return f"Synced with GitHub: pulled the latest from the scheduled runs, {pushed}.{note}"


def make_handler(app):
    failed_logins = []  # when wrong passwords were tried

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            logging.debug(fmt, *args)

        def _send(self, code, body, content_type="application/json", headers=()):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            for name, value in headers:
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(data)

        def _redirect(self, location, login=False):
            headers = [("Location", location)]
            if login:
                secure = self.headers.get("X-Forwarded-Proto") == "https" or "https" in (self.headers.get("Cf-Visitor") or "")
                cookie = f"office_key={phone.login_key(app.password)}; Path=/; Max-Age=2592000; HttpOnly; SameSite=Lax"
                headers.append(("Set-Cookie", cookie + ("; Secure" if secure else "")))
            self._send(303, b"", "text/plain", headers)

        def _local(self):
            return (self.headers.get("Host") or "").rsplit(":", 1)[0] in LOCAL_HOSTS

        def _this_computer(self):
            """A request from a browser on this computer, not relayed by a tunnel."""
            relayed = any(self.headers.get(h) for h in PROXY_HEADERS)
            return self.client_address[0] in LOOPBACK and self._local() and not relayed

        def _logged_in(self):
            cookie = SimpleCookie(self.headers.get("Cookie") or "")
            sent = cookie["office_key"].value if "office_key" in cookie else ""
            return hmac.compare_digest(sent, phone.login_key(app.password))

        def _allowed(self):
            if app.password is None:
                return self._local() or app.any_host
            return self._this_computer() or self._logged_in()

        def do_GET(self):
            url = urlparse(self.path)
            parts = [p for p in url.path.split("/") if p]
            if app.password is not None and parts == ["login"]:
                return self._send(200, (STATIC / "login.html").read_bytes(), "text/html; charset=utf-8")
            if not self._allowed():
                if app.password is None:
                    return self._send(403, {"error": "local requests only"})
                key = parse_qs(url.query).get("key", [""])[0]
                if key and hmac.compare_digest(key, phone.login_key(app.password)):  # the QR code's link
                    return self._redirect("/", login=True)
                return self._redirect("/login") if not parts else self._send(401, {"error": "log in first"})
            try:
                if not parts:
                    return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
                if parts == ["api", "phone"]:  # the phone links, with the login key: this computer only
                    return self._send(200, app.phone_links() if self._this_computer() else {"links": []})
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
                if parts[0] == "media" and len(parts) == 4 and parts[3].startswith("picture_"):
                    path = app.picture(parts[1], int(parts[2]), parts[3])
                    if path:
                        return self._send(200, path.read_bytes(), "image/png")
                return self._send(404, {"error": "not found"})
            except (KeyError, ValueError) as e:
                return self._send(404, {"error": str(e)})

        def do_POST(self):
            parts = [p for p in urlparse(self.path).path.split("/") if p]
            length = int(self.headers.get("Content-Length") or 0)
            if app.password is not None and parts == ["login"]:
                return self._login(self.rfile.read(min(length, 4096)))
            if not self._allowed() or self.headers.get("X-Office") != "1":
                return self._send(403, {"error": "local office requests only"})
            if parts[:2] == ["api", "upload"] and len(parts) == 5:  # a video clip, sent as the raw body
                if length > MAX_UPLOAD:
                    return self._send(413, {"error": "That clip is too big (over 500 MB)."})
                try:
                    data = self.rfile.read(length)
                    app.add_clip(parts[2], int(parts[3]), int(parts[4]), data, unquote(self.headers.get("X-Filename", "")))
                    return self._send(200, {"ok": True})
                except (KeyError, ValueError) as e:
                    return self._send(400, {"error": str(e)})
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

        def _login(self, body):
            now = time.monotonic()
            failed_logins[:] = [t for t in failed_logins if now - t < 60]
            if len(failed_logins) >= LOGIN_TRIES_PER_MINUTE:
                return self._redirect("/login?wait=1")
            tried = parse_qs(body.decode("utf-8", "replace")).get("password", [""])[0]
            if hmac.compare_digest(tried.encode(), app.password.encode()):
                return self._redirect("/", login=True)
            failed_logins.append(now)
            time.sleep(1)
            return self._redirect("/login?wrong=1")

    return Handler


def serve(app, port=8765, checkin_minutes=30, host="127.0.0.1"):
    server = ThreadingHTTPServer((host, port), make_handler(app))

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
