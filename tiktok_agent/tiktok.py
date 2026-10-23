"""Send videos to the creator's TikTok inbox with the Content Posting API.

Uploads go to the inbox as drafts (scope video.upload): TikTok notifies you in the app, where you
add sound and text, set the "AI-generated" label and post. Posting directly (video.publish)
needs TikTok to audit the app; until then direct posts can only be private.
"""

import logging
import os
import secrets
from pathlib import Path
from urllib.parse import urlencode

import requests

API = "https://open.tiktokapis.com/v2"
AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
SCOPES = "user.info.basic,video.upload"
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


def authorize_url(redirect_uri):
    query = {
        "client_key": _env("TIKTOK_CLIENT_KEY"),
        "scope": SCOPES,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": secrets.token_urlsafe(16),
    }
    return f"{AUTHORIZE_URL}?{urlencode(query)}"


def exchange_code(code, redirect_uri, session=None):
    return _token({"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri}, session)


def refresh_access_token(session=None):
    refresh_token = _env("TIKTOK_REFRESH_TOKEN")
    tokens = _token({"grant_type": "refresh_token", "refresh_token": refresh_token}, session)
    if tokens.get("refresh_token") and tokens["refresh_token"] != refresh_token:
        # Never log the token itself: workflow logs of a public repo are public.
        logging.warning("TikTok issued a new refresh token. If uploads start failing, run auth again and update TIKTOK_REFRESH_TOKEN.")
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
        raise SystemExit(f"Set {name} (TikTok developer portal -> your app; see README).")
    return value
