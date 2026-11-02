"""The work behind each desk: one content queue per channel and what can be done with it.

Agents call the read and drafting methods through their tools. approve() and publish() are only
reachable from the buttons in the office, so nothing goes out without a click from the owner.
"""

import argparse
import os
import shutil
import tempfile
import threading
from pathlib import Path

import taste
from shorts import cli as shorts_cli
from shorts import images, plans, render
from x_agent import brain, text
from x_agent.queue import PostQueue
from x_agent.x_client import ENV_KEYS, XClient, XError, post_url

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

    def reject(self, item_id, reason=""):
        with self.lock:
            q = self.queue()
            if q.get(item_id)["status"] in self.published:
                raise ValueError(f"#{item_id} is already published")
            q.set_status(item_id, "rejected", **({"reject_reason": str(reason).strip()[:300]} if str(reason).strip() else {}))
            q.save()

    def restore(self, item_id):
        """Bring a rejected item back as a draft. Button only."""
        with self.lock:
            q = self.queue()
            if q.get(item_id)["status"] != "rejected":
                raise ValueError(f"#{item_id} isn't rejected")
            q.set_status(item_id, "draft", error="")
            q.save()

    def editable(self, item):
        return item["status"] not in (*self.published, "rejected")

    def edit(self, item_id, changes):
        """Your own wording for an item: the hook plus the desk's own fields. Button only."""
        with self.lock:
            q = self.queue()
            item = q.get(item_id)
            if not self.editable(item):
                raise ValueError(f"#{item_id} is {item['status']} and can't be edited")
            hook = str(changes.get("hook", item["hook"])).strip()
            if not hook:
                raise ValueError("The title can't be empty")
            item["hook"] = hook
            self._edit(item, changes)
            item["owner_wording"] = self._wording(item)  # the team learns the owner's style from it
            if item["status"] == "approved" and self.problems(item):
                q.set_status(item_id, "draft")  # approve it again once it fits
            q.save()
            return item

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

    def api_ready(self):
        """Posting through X's API costs money; without its keys you post yourself, for free."""
        return self.x_client is not None or all(os.environ.get(k) for k in ENV_KEYS)

    def _edit(self, item, changes):
        if item.get("tweet_ids"):
            raise ValueError(f"#{item['id']} is already partly on X")
        posts = [str(p).strip() for p in changes.get("posts", item["posts"])]
        if not posts or not all(posts):
            raise ValueError("Every post in the thread needs text")
        item["posts"] = posts

    def _wording(self, item):
        return " / ".join(item["posts"])[:400]

    def mark_posted(self, item_id):
        """You posted it yourself from the 'Open in X' button."""
        with self.lock:
            q = self.queue()
            if q.get(item_id)["status"] != "approved":
                raise ValueError(f"#{item_id} must be approved first")
            q.set_status(item_id, "posted", posted_by="owner", error="")
            q.save()

    def create_drafts(self, count, theme=""):
        q = self.queue()
        profile = taste.with_taste(brain.load_profile(), self.key, q.items)
        ideas = brain.generate_ideas(profile, count, theme, q.recent_hooks(), True, self.claude)
        for idea in ideas:
            if text.problems(idea["posts"]):
                idea.update(brain.revise(profile, idea, "Fix this: " + "; ".join(text.problems(idea["posts"])), self.claude))
        return self._add_all(ideas)

    def revise(self, item_id, feedback):
        item = self.item(item_id)
        if item.get("tweet_ids"):
            raise ValueError(f"#{item_id} is already on X")
        new = brain.revise(taste.with_taste(brain.load_profile(), self.key, self.queue().items), item, feedback, self.claude)
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

    def __init__(self, platform, queue_path=None, claude=None, hf=None, client=None, assemble=None, stock=None, pictures=None):
        super().__init__()
        self.stock = stock  # the stock-site session (tests pass a fake)
        self.pictures = pictures  # the AI picture maker (tests pass a fake)
        self.platform, self.queue_path = platform, queue_path
        self.key, self.title = platform.name, platform.title
        self.claude, self.hf, self.client, self.assemble = claude, hf, client, assemble

    def queue(self):
        return self.platform.queue(self.queue_path)

    def problems(self, item):
        return plans.problems(self.platform, item)

    def create_drafts(self, count, theme=""):
        q = self.queue()
        profile = taste.with_taste(self.platform.profile, self.key, q.items)
        ideas = plans.generate(self.platform, profile, count, theme, q.recent_hooks(), True, self.claude,
                               searches=plans.recent_searches(q.items))
        for idea in ideas:
            if plans.problems(self.platform, idea):
                fix = "Fix this: " + "; ".join(plans.problems(self.platform, idea))
                idea.update(plans.revise(self.platform, profile, idea, fix, self.claude))
        return self._add_all(ideas)

    def revise(self, item_id, feedback):
        item = self.item(item_id)
        if item.get("clips") and not shorts_cli.is_free(item):  # paid AI clips are never thrown away
            raise ValueError(f"#{item_id} is already rendered; plan a new video instead")
        if item["status"] in self.published:
            raise ValueError(f"#{item_id} is already published; plan a new video instead")
        profile = taste.with_taste(self.platform.profile, self.key, self.queue().items)
        new = plans.revise(self.platform, profile, item, feedback, self.claude)
        with self.lock:
            q = self.queue()
            q.get(item_id).update(new, status="draft")
            q.get(item_id).pop("clips", None)  # stock clips or pictures are made again for the new plan
            q.save()
        return self.item(item_id)

    def _edit(self, item, changes):
        if "caption" in changes:
            item["caption"] = str(changes["caption"]).strip()
        if "texts" in changes:
            texts = [str(t).strip() for t in changes["texts"]]
            if len(texts) != len(item["shots"]) or not all(texts):
                raise ValueError("Every shot needs its on-screen text")
            changed = [s["on_screen_text"] for s in item["shots"]] != texts
            for shot, words in zip(item["shots"], texts):
                shot["on_screen_text"] = words
            if changed and item["status"] == "rendered":  # the words are burned into the video: make it again
                item["status"] = "approved"
                self.video_path(item["id"]).unlink(missing_ok=True)

    def _wording(self, item):
        texts = " / ".join(s["on_screen_text"] for s in item["shots"])
        return f"on screen: {texts}; caption: {item.get('caption', '')}"[:400]

    def copy_to(self, other, item_id):
        """The same approved video for the other platform: no new plan, no new pictures. Button only."""
        item = self.item(item_id)
        if item["status"] not in ("approved", "rendered", "sent", "posted"):
            raise ValueError(f"#{item_id} needs to be approved first")
        if item.get("copied_to"):
            raise ValueError(f"#{item_id} is already on {other.title}")
        plan = {k: item[k] for k in ("pillar", "hook", "shots", "voiceover", "caption", "sources", "fact_check") if k in item}
        with other.lock:
            q = other.queue()
            new = q.add(plan, status="approved")
            new.update(copied_from=f"{self.key}:{item_id}", approved_by="office")
            if item.get("clips"):
                new["clips"] = item["clips"]
            source, target = self.video_path(item_id).parent, other.video_path(new["id"]).parent
            for folder in ("pictures", "uploads"):  # the AI pictures and your own clips come along
                if (source / folder).is_dir():
                    shutil.copytree(source / folder, target / folder, dirs_exist_ok=True)
            if self.video_path(item_id).exists():  # already made: the other platform gets the same video
                target.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(self.video_path(item_id), other.video_path(new["id"]))
                q.set_status(new["id"], "rendered")
            q.save()
        with self.lock:
            q = self.queue()
            q.get(item_id)["copied_to"] = f"{other.key}:{new['id']}"
            q.save()
        return new

    def mark_posted(self, item_id, url=""):
        """You posted the video yourself (downloaded it, or finished it from your TikTok inbox). Button only."""
        with self.lock:
            q = self.queue()
            if q.get(item_id)["status"] not in ("rendered", "sent"):
                raise ValueError(f"#{item_id} needs a finished video first")
            q.set_status(item_id, "posted", posted_by="owner", error="", **({"url": url} if url else {}))
            q.save()

    def caption_to_post(self, item):
        """The caption as it should go out: with stock-clip credits, or (Instagram) an AI note."""
        if self.key == "instagram":
            from instagram_agent.__main__ import final_caption

            return final_caption(item)
        credit = render.credits(item.get("clips", []))
        return f"{item['caption']}\n\n{credit}" if credit else item["caption"]

    def render(self, item_id):
        """Make the video without publishing it (spends Higgsfield credits). Button only."""
        return self._make(item_id, no_upload=True)

    def publish(self, item_id):
        """Render if needed, then publish (TikTok inbox or Instagram Reel). Button only."""
        return self._make(item_id, no_upload=False)

    def new_clips(self, item_id):
        """Stock videos: swap the clips for different free footage and render again. Button only."""
        return self._make(item_id, no_upload=True, new_clips=True)

    def uploads(self, item):
        """For plans made from your own clips: which shots have one (True/False), else None."""
        if not shorts_cli.is_upload(item):
            return None
        return [f is not None for f in render.uploaded(shorts_cli.upload_folder(self.platform, item["id"]), len(item["shots"]))]

    def add_clip(self, item_id, shot, data, filename):
        """Keep the clip you made for one shot of a plan. Button only."""
        item = self.item(item_id)
        if not shorts_cli.is_upload(item):
            raise ValueError(f"#{item_id} doesn't take your own clips")
        if item["status"] in self.published:
            raise ValueError(f"#{item_id} is already published")
        if not 1 <= int(shot) <= len(item["shots"]):
            raise ValueError(f"#{item_id} has no shot {shot}")
        with self.lock:
            return render.save_upload(shorts_cli.upload_folder(self.platform, item_id), int(shot), data, filename)

    def picture_shot(self, item_id, shot):
        """No clip for a shot (the video site's daily credits ran out, say)? Draw it as a free AI
        picture with a camera move, and use that as the shot's clip. Button only."""
        item = self.item(item_id)
        if not shorts_cli.is_upload(item):
            raise ValueError(f"#{item_id} doesn't take your own clips")
        if item["status"] in self.published:
            raise ValueError(f"#{item_id} is already published")
        if not 1 <= int(shot) <= len(item["shots"]):
            raise ValueError(f"#{item_id} has no shot {shot}")
        pictures = self.pictures or images.CloudflareImages()
        with tempfile.TemporaryDirectory() as tmp:
            picture = Path(tmp) / "picture.png"
            picture.write_bytes(pictures.generate(item["shots"][int(shot) - 1]["video_prompt"]))
            clip = images.camera_move(picture, Path(tmp) / "clip.mp4", self.platform.seconds + render.FADE,
                                      images.CAMERA[(int(shot) - 1) % len(images.CAMERA)])  # fmt: skip
            with self.lock:
                return render.save_upload(shorts_cli.upload_folder(self.platform, item_id), int(shot), clip.read_bytes(), "ai-picture.mp4")

    def video_path(self, item_id):
        return Path("build") / self.platform.name / str(int(item_id)) / "video.mp4"

    def _make(self, item_id, no_upload, new_clips=False):
        with self.lock:
            q = self.queue()
            args = argparse.Namespace(id=int(item_id), no_upload=no_upload, new_clips=new_clips)
            code = shorts_cli.cmd_make(self.platform, q, args, self.hf, self.client, self.assemble, self.stock, self.pictures)
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
