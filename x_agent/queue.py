"""The content queue: a JSON file of ideas/drafts and what happened to them.

Status flow: draft -> approved -> posted. Drafts can also be rejected; a post that fails on X
is marked failed with the error. Rejected and posted items stay in the file so the agent
doesn't suggest the same idea twice.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_PATH = "content/x_queue.json"
STATUSES = ("draft", "approved", "posted", "rejected", "failed")


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class PostQueue:
    def __init__(self, path=None):
        self.path = Path(path or os.environ.get("X_QUEUE") or DEFAULT_PATH)
        self.items = json.loads(self.path.read_text()) if self.path.exists() else []

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.items, indent=2, ensure_ascii=False) + "\n")

    def add(self, idea, status="draft"):
        item = {
            "id": max((i["id"] for i in self.items), default=0) + 1,
            "status": status,
            "pillar": idea.get("pillar", ""),
            "hook": idea["hook"],
            "posts": list(idea["posts"]),
            "sources": list(idea.get("sources", [])),
            "fact_check": idea.get("fact_check", ""),
            "created_at": now_iso(),
        }
        self.items.append(item)
        return item

    def get(self, item_id):
        for item in self.items:
            if item["id"] == int(item_id):
                return item
        raise KeyError(f"no queue item with id {item_id}")

    def with_status(self, *statuses):
        return [i for i in self.items if i["status"] in statuses]

    def next_approved(self):
        approved = self.with_status("approved")
        return min(approved, key=lambda i: (i.get("approved_at", ""), i["id"]), default=None)

    def set_status(self, item_id, status, **fields):
        assert status in STATUSES, status
        item = self.get(item_id)
        item["status"] = status
        item[f"{status}_at"] = now_iso()
        item.update(fields)
        return item

    def recent_hooks(self, n=40):
        return [i["hook"] for i in self.items[-n:]]
