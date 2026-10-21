"""Publish posts and threads with the X API v2 (OAuth 1.0a user context)."""

import os

TWEETS_URL = "https://api.x.com/2/tweets"
TIMEOUT_S = 30
ENV_KEYS = ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET")


class XError(RuntimeError):
    def __init__(self, message, posted_ids=()):
        super().__init__(message)
        self.posted_ids = list(posted_ids)  # thread posts that went out before the failure


class XClient:
    def __init__(self, session):
        self.session = session

    @classmethod
    def from_env(cls):
        from requests_oauthlib import OAuth1Session

        missing = [k for k in ENV_KEYS if not os.environ.get(k)]
        if missing:
            raise SystemExit(f"Set {', '.join(missing)} (X developer portal -> your app -> Keys and tokens).")
        key, secret, token, token_secret = (os.environ[k] for k in ENV_KEYS)
        return cls(OAuth1Session(key, client_secret=secret, resource_owner_key=token, resource_owner_secret=token_secret))

    def post_thread(self, texts):
        """Post texts in order, each replying to the previous one. Returns the post ids."""
        ids = []
        for text in texts:
            payload = {"text": text}
            if ids:
                payload["reply"] = {"in_reply_to_tweet_id": ids[-1]}
            resp = self.session.post(TWEETS_URL, json=payload, timeout=TIMEOUT_S)
            if resp.status_code >= 400:
                raise XError(f"X API {resp.status_code}: {resp.text[:500]}", ids)
            ids.append(resp.json()["data"]["id"])
        return ids


def post_url(post_id):
    return f"https://x.com/i/web/status/{post_id}"
