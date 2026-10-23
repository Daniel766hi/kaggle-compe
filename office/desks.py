"""The work behind each desk: one content queue per channel and what can be done with it.

Agents call the read and drafting methods through their tools. approve() and publish() are only
reachable from the buttons in the office, so nothing goes out without a click from the owner.
"""

import argparse
import threading
from pathlib import Path

from shorts import cli as shorts_cli
from shorts import plans
from x_agent import brain, text
from x_agent.queue import PostQueue
from x_agent.x_client import XClient, XError, post_url

WAITING = ("draft", "approved", "rendered", "failed")


class Desk:
    key = title = ""
    published = ("posted",)

    def __init__(self):
        self.lock = threading.Lock()  # one writer at a time; readers load the (atomically saved) file

    def queue(self):
        raise NotImplementedError

    def items(self, status="waiting"):
        q = self.queue()
        if status == "all":
            return q.items
        return q.with_status(*(WAITING if status == "waiting" else (status,)))

    def item(self, item_id):
        return self.queue().get(item_id)

    def counts(self):
        out = {}
        for item in self.queue().items:
            out[item["status"]] = out.get(item["status"], 0) + 1
        return out

    def reject(self, item_id):
        with self.lock:
            q = self.queue()
            if q.get(item_id)["status"] in self.published:
                raise ValueError(f"#{item_id} is already published")
            q.set_status(item_id, "rejected")
            q.save()

    def approve(self, item_id):
        with self.lock:
            q = self.queue()
            item = q.get(item_id)
            if item["status"] not in ("draft", "failed"):
                raise ValueError(f"#{item_id} is {item['status']}")
            if self.problems(item):
                raise ValueError(f"#{item_id} can't be approved: {'; '.join(self.problems(item))}")
            q.set_status(item_id, "approved", approved_by="office")
            q.save()

    def _add_all(self, ideas):
        with self.lock:
            q = self.queue()
            added = [q.add(idea) for idea in ideas]
            q.save()
        return added


class XDesk(Desk):
    key, title = "x", "X"

    def __init__(self, queue_path=None, claude=None, x_client=None):
        super().__init__()
        self.queue_path, self.claude, self.x_client = queue_path, claude, x_client

    def queue(self):
        return PostQueue(self.queue_path)

    def problems(self, item):
        return text.problems(item["posts"])

    def create_drafts(self, count, theme=""):
        profile = brain.load_profile()
        ideas = brain.generate_ideas(profile, count, theme, self.queue().recent_hooks(), True, self.claude)
        for idea in ideas:
            if text.problems(idea["posts"]):
                idea.update(brain.revise(profile, idea, "Fix this: " + "; ".join(text.problems(idea["posts"])), self.claude))
        return self._add_all(ideas)

    def revise(self, item_id, feedback):
        item = self.item(item_id)
        if item.get("tweet_ids"):
            raise ValueError(f"#{item_id} is already on X")
        new = brain.revise(brain.load_profile(), item, feedback, self.claude)
        with self.lock:
            q = self.queue()
            q.get(item_id).update(new, status="draft")
            q.save()
        return self.item(item_id)

    def publish(self, item_id):
        """Post now. Only called from the office's Post button."""
        with self.lock:
            q = self.queue()
            item = q.get(item_id)
            if item["status"] != "approved":
                raise ValueError(f"#{item_id} must be approved first")
            client = self.x_client or XClient.from_env()
            try:
                ids = client.post_thread(item["posts"])
            except XError as e:
                fields = {"error": str(e)}
                if e.posted_ids:
                    fields.update(tweet_ids=e.posted_ids, url=post_url(e.posted_ids[0]))
                q.set_status(item_id, "failed", **fields)
                q.save()
                raise
            q.set_status(item_id, "posted", tweet_ids=ids, url=post_url(ids[0]), error="")
            q.save()
            return q.get(item_id)


class VideoDesk(Desk):
    published = ("sent", "posted")

    def __init__(self, platform, queue_path=None, claude=None, hf=None, client=None, assemble=None):
        super().__init__()
        self.platform, self.queue_path = platform, queue_path
        self.key, self.title = platform.name, platform.title
        self.claude, self.hf, self.client, self.assemble = claude, hf, client, assemble

    def queue(self):
        return self.platform.queue(self.queue_path)

    def problems(self, item):
        return plans.problems(self.platform, item)

    def create_drafts(self, count, theme=""):
        profile = self.platform.profile
        ideas = plans.generate(self.platform, profile, count, theme, self.queue().recent_hooks(), True, self.claude)
        for idea in ideas:
            if plans.problems(self.platform, idea):
                fix = "Fix this: " + "; ".join(plans.problems(self.platform, idea))
                idea.update(plans.revise(self.platform, profile, idea, fix, self.claude))
        return self._add_all(ideas)

    def revise(self, item_id, feedback):
        item = self.item(item_id)
        if item.get("clips"):
            raise ValueError(f"#{item_id} is already rendered; plan a new video instead")
        new = plans.revise(self.platform, self.platform.profile, item, feedback, self.claude)
        with self.lock:
            q = self.queue()
            q.get(item_id).update(new, status="draft")
            q.save()
        return self.item(item_id)

    def render(self, item_id):
        """Make the video without publishing it (spends Higgsfield credits). Button only."""
        return self._make(item_id, no_upload=True)

    def publish(self, item_id):
        """Render if needed, then publish (TikTok inbox or Instagram Reel). Button only."""
        return self._make(item_id, no_upload=False)

    def video_path(self, item_id):
        return Path("build") / self.platform.name / str(int(item_id)) / "video.mp4"

    def _make(self, item_id, no_upload):
        with self.lock:
            q = self.queue()
            code = shorts_cli.cmd_make(
                self.platform, q, argparse.Namespace(id=int(item_id), no_upload=no_upload), self.hf, self.client, self.assemble
            )
            q.save()
            item = q.get(item_id)
        if code:
            raise RuntimeError(item.get("error") or "the video could not be made")
        return item


def summary(desk, item, full=False):
    """What an agent (or the office) needs to know about an item."""
    out = {"id": item["id"], "status": item["status"], "hook": item["hook"]}
    if item.get("fact_check"):
        out["fact_check"] = item["fact_check"]
    if item.get("error"):
        out["error"] = item["error"]
    if item.get("url"):
        out["url"] = item["url"]
    problems = desk.problems(item) if item["status"] not in desk.published else []
    if problems:
        out["problems"] = problems
    if full:
        for key in ("pillar", "posts", "shots", "voiceover", "caption", "sources"):
            if key in item:
                out[key] = item[key]
    return out
