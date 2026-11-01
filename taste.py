"""What the owner likes, so the team learns their taste.

Every time an agent plans or rewrites something, the channel's brief gets a short section built
from the owner's own signals: their standing notes for that channel, the ideas they approved,
the ideas they rejected (with the reason, when they gave one) and the text they rewrote
themselves. Notes live in content/notes/<channel>.md, which is synced to GitHub, so the daily
runs follow them too.
"""

from pathlib import Path

NOTES_DIR = Path("content") / "notes"
LIKED = ("approved", "rendered", "sent", "posted")
MAX_NOTES = 4000


def notes_path(key):
    return NOTES_DIR / f"{key}.md"


def read_notes(key):
    path = notes_path(key)
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def save_notes(key, text):
    text = str(text).strip()
    if len(text) > MAX_NOTES:
        raise ValueError(f"Notes are limited to {MAX_NOTES} characters")
    path = notes_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text + "\n" if text else "", encoding="utf-8")
    tmp.replace(path)


def summary(key, items, n=8):
    """The owner's signals for one channel, as plain text ('' when there are none yet)."""
    parts = []
    notes = read_notes(key)
    if notes:
        parts.append("The owner's standing notes for this channel (always follow them):\n" + notes)
    liked = [i for i in items if i["status"] in LIKED][-n:]
    if liked:
        parts.append("Ideas the owner approved (more in this spirit, but never repeat them):\n"
                     + "\n".join(f"- {i['hook']}" for i in liked))  # fmt: skip
    rejected = [i for i in items if i["status"] == "rejected"][-n:]
    if rejected:
        parts.append("Ideas the owner rejected (avoid what made them miss):\n" + "\n".join(
            f"- {i['hook']}" + (f" (why: {i['reject_reason']})" if i.get("reject_reason") else "") for i in rejected))  # fmt: skip
    edited = [i for i in items if i.get("owner_wording")][-4:]
    if edited:
        parts.append("The owner rewrote these in their own words; match their wording and tone:\n"
                     + "\n".join(f"- {i['owner_wording']}" for i in edited))  # fmt: skip
    return "\n\n".join(parts)


def with_taste(profile, key, items):
    """The channel brief plus what the owner likes."""
    learned = summary(key, items)
    return f"{profile}\n\n## What the owner likes (learned from their reviews)\n\n{learned}" if learned else profile
