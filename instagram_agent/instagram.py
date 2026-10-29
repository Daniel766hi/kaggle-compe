"""Publish Reels with the Instagram Graph API (Facebook Login for Business).

The video file is sent with Meta's resumable upload, so it doesn't need to be hosted anywhere.
That upload is available with Facebook Login (graph.facebook.com), which needs the Instagram
professional account to be linked to a Facebook Page. Permissions: instagram_basic,
instagram_content_publish, pages_show_list, pages_read_engagement.
"""

import os
import time
from pathlib import Path

import requests

VERSION = os.environ.get("INSTAGRAM_GRAPH_VERSION") or "v26.0"
GRAPH = f"https://graph.facebook.com/{VERSION}"
RUPLOAD = f"https://rupload.facebook.com/ig-api-upload/{VERSION}"
TIMEOUT_S = 120
MAX_BYTES = 300 * 1024 * 1024  # Reels limit
POLL_S, MAX_WAIT_S = 10, 15 * 60


class InstagramError(RuntimeError):
    pass


class InstagramClient:
    def __init__(self, user_id, access_token, session=None, sleep=time.sleep):
        self.user_id, self.token = user_id, access_token
        self.session = session or requests.Session()
        self.sleep = sleep

    @classmethod
    def from_env(cls):
        missing = [k for k in ("INSTAGRAM_USER_ID", "INSTAGRAM_ACCESS_TOKEN") if not os.environ.get(k)]
        if missing:
            raise SystemExit(f"Set {', '.join(missing)}: run `python -m instagram_agent login` (it walks you through it).")
        return cls(os.environ["INSTAGRAM_USER_ID"], os.environ["INSTAGRAM_ACCESS_TOKEN"])

    def publish_reel(self, path, caption):
        """Upload, wait for Instagram to process it, publish. Returns the media id and link."""
        size = Path(path).stat().st_size
        if size > MAX_BYTES:
            raise InstagramError(f"video is {size / 2**20:.0f} MB; Reels allow 300 MB")
        quota = self.quota()
        if quota["used"] >= quota["total"]:
            raise InstagramError(f"publishing limit reached ({quota['used']}/{quota['total']} in 24 hours)")

        container = self._call("POST", f"/{self.user_id}/media", {
            "media_type": "REELS", "upload_type": "resumable", "caption": caption, "share_to_feed": "true",
        })["id"]  # fmt: skip
        with open(path, "rb") as f:
            headers = {"Authorization": f"OAuth {self.token}", "offset": "0", "file_size": str(size)}
            resp = self.session.post(f"{RUPLOAD}/{container}", data=f.read(), headers=headers, timeout=TIMEOUT_S)
        if resp.status_code >= 400:
            raise InstagramError(f"video upload failed: HTTP {resp.status_code} {resp.text[:300]}")

        waited = 0
        while True:
            state = self._call("GET", f"/{container}", {"fields": "status_code,status"})
            if state.get("status_code") == "FINISHED":
                break
            if state.get("status_code") in ("ERROR", "EXPIRED") or waited >= MAX_WAIT_S:
                raise InstagramError(f"Instagram couldn't process the video: {state.get('status') or state}")
            self.sleep(POLL_S)
            waited += POLL_S

        media_id = self._call("POST", f"/{self.user_id}/media_publish", {"creation_id": container})["id"]
        try:  # the Reel is live now; a failed lookup must not mark it failed (a retry would post it twice)
            link = self._call("GET", f"/{media_id}", {"fields": "permalink"}).get("permalink", "")
        except (InstagramError, requests.RequestException):
            link = ""
        return {"media_id": media_id, "url": link}

    def quota(self):
        data = self._call("GET", f"/{self.user_id}/content_publishing_limit", {"fields": "config,quota_usage"})
        limit = (data.get("data") or [{}])[0]
        return {"used": limit.get("quota_usage", 0), "total": (limit.get("config") or {}).get("quota_total", 100)}

    def _call(self, method, path, params):
        params = {**params, "access_token": self.token}
        if method == "GET":
            resp = self.session.get(GRAPH + path, params=params, timeout=TIMEOUT_S)
        else:
            resp = self.session.post(GRAPH + path, data=params, timeout=TIMEOUT_S)
        return _json_or_raise(resp)


def connect(app_id, app_secret, short_token, session=None):
    """Exchange a short-lived user token (Graph API Explorer) for the IDs and token the agent needs.

    Returns one entry per Facebook Page that has an Instagram professional account linked. A Page
    token obtained from a long-lived user token does not expire.
    """
    session = session or requests.Session()
    long_user = _json_or_raise(session.get(f"{GRAPH}/oauth/access_token", params={
        "grant_type": "fb_exchange_token", "client_id": app_id, "client_secret": app_secret, "fb_exchange_token": short_token,
    }, timeout=TIMEOUT_S))["access_token"]  # fmt: skip
    pages = _json_or_raise(session.get(f"{GRAPH}/me/accounts", params={
        "fields": "name,access_token,instagram_business_account{id,username}", "access_token": long_user,
    }, timeout=TIMEOUT_S)).get("data", [])  # fmt: skip
    return [
        {
            "page": page["name"],
            "username": page["instagram_business_account"].get("username", ""),
            "user_id": page["instagram_business_account"]["id"],
            "access_token": page["access_token"],
        }
        for page in pages
        if page.get("instagram_business_account")
    ]


def _json_or_raise(resp):
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if resp.status_code >= 400 or "error" in body:
        error = body.get("error") or {}
        raise InstagramError(f"Instagram API {resp.status_code}: {error.get('message') or resp.text[:300]}")
    return body
