"""Send videos to the creator's TikTok inbox with the Content Posting API.

Uploads go to the inbox as drafts (scope video.upload): TikTok notifies you in the app, where you
add sound and text, set the "AI-generated" label and post. Posting directly (video.publish)
needs TikTok to audit the app; until then direct posts can only be private.
"""

import hashlib
import logging
import os
import secrets
import string
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests

import local_env

API = "https://open.tiktokapis.com/v2"
AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
SCOPES = "user.info.basic,video.upload"
# Register exactly this in your app: Login Kit -> Desktop -> Redirect URI (see `python -m tiktok_agent login`).
DESKTOP_REDIRECT = "http://127.0.0.1:3455/callback/"
LOGIN_PORT = 3455
MAX_SINGLE_CHUNK = 64 * 1024 * 1024  # TikTok chunks are 5-64 MB; smaller files go up whole
CHUNK = 32 * 1024 * 1024
TIMEOUT_S = 120


class TikTokError(RuntimeError):
    pass


def chunk_plan(size):
    """(chunk_size, chunk_count) as TikTok expects them; the last chunk takes the remainder."""
    if size <= MAX_SINGLE_CHUNK:
        return size, 1
    return CHUNK, size // CHUNK


class TikTokClient:
    def __init__(self, access_token, session=None):
        self.session = session or requests.Session()
        self.session.headers["Authorization"] = f"Bearer {access_token}"

    @classmethod
    def from_env(cls, session=None):
        token = os.environ.get("TIKTOK_ACCESS_TOKEN")
        if not token:
            token = refresh_access_token(session)["access_token"]
        return cls(token, session)

    def upload_draft(self, path):
        """Upload an mp4 to the inbox. Returns the publish_id to check its status."""
        size = Path(path).stat().st_size
        chunk_size, count = chunk_plan(size)
        data = self._post("/post/publish/inbox/video/init/", {
            "source_info": {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": chunk_size, "total_chunk_count": count},
        })  # fmt: skip
        with open(path, "rb") as f:
            for i in range(count):
                start = i * chunk_size
                body = f.read() if i == count - 1 else f.read(chunk_size)
                end = start + len(body) - 1
                headers = {"Content-Type": "video/mp4", "Content-Length": str(len(body)), "Content-Range": f"bytes {start}-{end}/{size}"}
                resp = self.session.put(data["upload_url"], data=body, headers=headers, timeout=TIMEOUT_S)
                if resp.status_code >= 400:
                    raise TikTokError(f"upload of bytes {start}-{end} failed: HTTP {resp.status_code} {resp.text[:300]}")
        return data["publish_id"]

    def status(self, publish_id):
        """e.g. {"status": "SEND_TO_USER_INBOX"}; FAILED comes with a fail_reason."""
        return self._post("/post/publish/status/fetch/", {"publish_id": publish_id})

    def _post(self, path, payload):
        resp = self.session.post(API + path, json=payload, timeout=TIMEOUT_S)
        body = resp.json() if resp.content else {}
        error = body.get("error") or {}
        if resp.status_code >= 400 or error.get("code", "ok") != "ok":
            raise TikTokError(f"TikTok {path} -> HTTP {resp.status_code} {error.get('code')}: {error.get('message', resp.text[:300])}")
        return body.get("data") or {}


def authorize_url(redirect_uri, state=None, code_challenge=None):
    query = {
        "client_key": _env("TIKTOK_CLIENT_KEY"),
        "scope": SCOPES,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state or secrets.token_urlsafe(16),
    }
    if code_challenge:  # desktop apps must use PKCE
        query.update(code_challenge=code_challenge, code_challenge_method="S256")
    return f"{AUTHORIZE_URL}?{urlencode(query)}"


def pkce_pair():
    """(code_verifier, code_challenge). TikTok wants the challenge as hex SHA-256, not base64."""
    verifier = "".join(secrets.choice(string.ascii_letters + string.digits + "-._~") for _ in range(64))
    return verifier, hashlib.sha256(verifier.encode()).hexdigest()


def exchange_code(code, redirect_uri, session=None, code_verifier=None):
    fields = {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri}
    if code_verifier:
        fields["code_verifier"] = code_verifier
    return _token(fields, session)


def login(open_browser=webbrowser.open, session=None, timeout_s=300):
    """The one-time TikTok login, as a desktop app: opens TikTok in the browser, catches the
    answer on this computer (DESKTOP_REDIRECT) and returns the tokens."""
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(16)
    answer, done = {}, threading.Event()

    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            url = urlparse(self.path)
            if url.path.rstrip("/") != "/callback":
                self.send_response(404)
                self.end_headers()
                return
            answer.update({k: v[0] for k, v in parse_qs(url.query).items()})
            ok = "code" in answer and answer.get("state") == state
            page = ("<h2>TikTok is connected.</h2><p>You can close this tab and go back to the office.</p>" if ok else
                    "<h2>TikTok login didn't finish.</h2><p>Go back to the terminal to see why.</p>")  # fmt: skip
            body = f"<!doctype html><meta charset=utf-8><body style='font-family:sans-serif;padding:24px'>{page}".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            done.set()

    try:
        server = HTTPServer(("127.0.0.1", LOGIN_PORT), Callback)
    except OSError as e:
        raise TikTokError(f"Port {LOGIN_PORT} is busy. Close the other TikTok login window and try again.") from e
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = authorize_url(DESKTOP_REDIRECT, state, challenge)
        print(f"Opening TikTok to log in. If no browser opens, copy this link into one:\n{url}\n")
        open_browser(url)
        if not done.wait(timeout_s):
            raise TikTokError("No answer from TikTok within 5 minutes. Run the login again.")
    finally:
        server.shutdown()
        server.server_close()
    if answer.get("error"):
        raise TikTokError(f"TikTok said: {answer.get('error')}: {answer.get('error_description', '')}".strip(": ")
                          + _login_hint(answer.get("error", "")))  # fmt: skip
    if answer.get("state") != state or "code" not in answer:
        raise TikTokError("TikTok's answer didn't match this login. Run the login again.")
    return exchange_code(answer["code"], DESKTOP_REDIRECT, session, verifier)


def _login_hint(error):
    if "redirect" in error or "param" in error:
        return f" (In your TikTok app, Login Kit -> Desktop -> Redirect URI must be exactly {DESKTOP_REDIRECT})"
    if "scope" in error:
        return " (Add the Content Posting API product to your app, with Upload turned on.)"
    if "access_denied" in error:
        return " (You pressed Cancel, or this TikTok account isn't a target user of the sandbox.)"
    return ""


def refresh_access_token(session=None):
    refresh_token = _env("TIKTOK_REFRESH_TOKEN")
    tokens = _token({"grant_type": "refresh_token", "refresh_token": refresh_token}, session)
    if tokens.get("refresh_token") and tokens["refresh_token"] != refresh_token:
        os.environ["TIKTOK_REFRESH_TOKEN"] = tokens["refresh_token"]
        if os.environ.get("GITHUB_ACTIONS"):
            # Never log the token itself: workflow logs of a public repo are public.
            logging.warning("TikTok issued a new refresh token. If uploads start failing, log in again and update TIKTOK_REFRESH_TOKEN.")
        else:  # on your computer: keep the new one
            local_env.save("TIKTOK_REFRESH_TOKEN", tokens["refresh_token"])
    return tokens


def _token(fields, session=None):
    session = session or requests.Session()
    form = {"client_key": _env("TIKTOK_CLIENT_KEY"), "client_secret": _env("TIKTOK_CLIENT_SECRET"), **fields}
    resp = session.post(f"{API}/oauth/token/", data=form, timeout=TIMEOUT_S)
    tokens = resp.json()
    if resp.status_code >= 400 or "access_token" not in tokens:
        raise TikTokError(f"TikTok token request failed: {tokens.get('error')}: {tokens.get('error_description')}")
    return tokens


def _env(name):
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Set {name}: run `python -m tiktok_agent login` (it walks you through it).")
    return value
