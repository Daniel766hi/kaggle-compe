"""Post length as X counts it."""

import os
import re

URL_RE = re.compile(r"https?://\S+")
URL_WEIGHT = 23  # X shortens every link to a t.co URL of this length
# Code point ranges X counts as one character; everything else (CJK, emoji) counts as two.
LIGHT_RANGES = ((0, 4351), (8192, 8205), (8208, 8223), (8242, 8247))


def max_chars():
    """280 for standard accounts; set X_MAX_CHARS=25000 for X Premium long posts."""
    return int(os.environ.get("X_MAX_CHARS") or 280)


def weighted_length(text):
    length = 0
    for part in URL_RE.split(text):
        length += sum(1 if any(lo <= ord(ch) <= hi for lo, hi in LIGHT_RANGES) else 2 for ch in part)
    return length + URL_WEIGHT * len(URL_RE.findall(text))


def problems(posts, limit=None):
    """Reasons a post or thread can't be published as is (empty list when it can)."""
    limit = limit or max_chars()
    if not posts:
        return ["no text"]
    out = []
    for i, post in enumerate(posts, 1):
        n = weighted_length(post)
        if not post.strip():
            out.append(f"post {i} is empty")
        elif n > limit:
            out.append(f"post {i} is {n} characters (limit {limit})")
    return out
