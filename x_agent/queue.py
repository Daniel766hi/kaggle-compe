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
    DEFAULT_PATH, PATH_ENV, STATUSES = DEFAULT_PATH, "X_QUEUE", STATUSES

    def __init__(self, path=None):
        self.path = Path(path or os.environ.get(self.PATH_ENV) or self.DEFAULT_PATH)
        self.items = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else []

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self.items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)  # readers never see a half-written file

    def add(self, idea, status="draft"):
        item = {
            "id": max((i["id"] for i in self.items), default=0) + 1,
            "status": status,
            "pillar": idea.get("pillar", ""),
            "hook": idea["hook"],
            **self._content(idea),
            "sources": list(idea.get("sources", [])),
            "fact_check": idea.get("fact_check", ""),
            "created_at": now_iso(),
        }
        self.items.append(item)
        return item

    def _content(self, idea):
        return {"posts": list(idea["posts"])}

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
        assert status in self.STATUSES, status
        item = self.get(item_id)
        item["status"] = status
        item[f"{status}_at"] = now_iso()
        item.update(fields)
        return item

    def recent_hooks(self, n=40):
        return [i["hook"] for i in self.items[-n:]]
