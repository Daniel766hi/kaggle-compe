import argparse
import json
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from shorts import cli, plans, render
from shorts.plans import VideoQueue
from tiktok_agent import tiktok
from tiktok_agent.__main__ import PLATFORM

from .test_x_agent import FakeClaude, message, text_block

SHOT = {"image_prompt": "Hazy Jakarta skyline at dawn", "motion_prompt": "slow push in", "on_screen_text": "Haze is back"}
PLAN = {
    "pillar": "Indonesia in data",
    "hook": "Why the haze comes every September",
    "shots": [SHOT, SHOT, SHOT],
    "voiceover": "Every September the sky over Sumatra turns grey.",
    "caption": "The haze calendar. #indonesia #data #haze",
    "sources": [],
    "fact_check": "",
}


class Completed:
    pass


class Failed:
    pass


class FakeHiggsfield:
    """Stands in for the higgsfield_client module."""

    Completed = Completed

    def __init__(self, fail_model=None):
        self.calls, self.fail_model = [], fail_model

    def submit(self, model, arguments):
        self.calls.append((model, arguments))
        n = len(self.calls)
        status = Failed() if model == self.fail_model else Completed()
        if model == render.IMAGE_MODEL:
            result = {"images": [{"url": f"https://img/{n}.png"}]}
        else:
            result = {"video": {"url": f"https://vid/{n}.mp4"}}
        return SimpleNamespace(poll_request_status=lambda: iter([status]), get=lambda: result)


class FakeResponse:
    def __init__(self, status, data):
        self.status_code, self._data = status, data
        self.text = json.dumps(data)
        self.content = self.text.encode()

    def json(self):
        return self._data


class FakeTikTokSession:
    def __init__(self, init_error=None):
        self.headers, self.posts, self.puts, self.init_error = {}, [], [], init_error

    def post(self, url, json=None, data=None, timeout=None):
        self.posts.append((url, json or data))
        if url.endswith("/oauth/token/"):
            return FakeResponse(200, {"access_token": "act", "refresh_token": "rft", "refresh_expires_in": 86400 * 365})
        if url.endswith("/status/fetch/"):
            return FakeResponse(200, {"data": {"status": "SEND_TO_USER_INBOX"}, "error": {"code": "ok"}})
        if self.init_error:
            return FakeResponse(403, {"error": {"code": self.init_error, "message": "nope"}})
        return FakeResponse(200, {"data": {"publish_id": "v_inbox_1", "upload_url": "https://upload"}, "error": {"code": "ok"}})

    def put(self, url, data, headers, timeout):
        self.puts.append((len(data), headers))
        return FakeResponse(201, {})


class FakeUploader:
    def __init__(self, fail=False):
        self.uploaded, self.fail = [], fail

    def upload_draft(self, path):
        if self.fail:
            raise tiktok.TikTokError("spam_risk_too_many_posts")
        self.uploaded.append(path)
        return "v_inbox_1"


def fake_assemble(clips, out_dir, **options):
    return out_dir / "video.mp4"


def test_plan_problems():
    assert plans.problems(PLATFORM, PLAN) == []
    long = {**PLAN, "shots": [SHOT], "voiceover": "word " * 40, "caption": "x" * 2201}
    assert plans.problems(PLATFORM, long) == [
        "1 shots planned, 3 expected",
        "voiceover is 40 words, 37 fit in 15s",
        "caption is 2201 characters (limit 2200)",
    ]


def test_render_makes_an_image_then_a_clip_per_shot():
    hf = FakeHiggsfield()
    clips = render.render(PLAN, 5, hf)
    assert len(clips) == 3 and len(hf.calls) == 6
    (image_model, image_args), (video_model, video_args) = hf.calls[:2]
    assert image_model == render.IMAGE_MODEL and image_args["aspect_ratio"] == "9:16"
    assert video_model == render.VIDEO_MODEL
    assert video_args == {"image_url": "https://img/1.png", "prompt": "slow push in", "duration": 5}
    assert clips[0] == {"image_url": "https://img/1.png", "video_url": "https://vid/2.mp4"}


def test_render_stops_on_a_failed_generation():
    with pytest.raises(render.RenderError, match="Failed"):
        render.render(PLAN, 5, FakeHiggsfield(fail_model=render.VIDEO_MODEL))


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_assemble_joins_clips_into_vertical_mp4(tmp_path):
    def make_clip(url, path):  # stands in for downloading: a 1 s test pattern of another size
        subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x480:rate=24:duration=1", str(path)], check=True)

    video = render.assemble([{"video_url": "a"}, {"video_url": "b"}], tmp_path / "out", download=make_clip)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=width,height,codec_name:format=duration", "-of", "json", str(video)],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    info = json.loads(probe.stdout)
    assert info["streams"] == [{"codec_name": "h264", "width": 1080, "height": 1920}]
    assert 1.9 < float(info["format"]["duration"]) < 2.2


def test_chunk_plan_follows_tiktok_rules():
    mb = 1024 * 1024
    assert tiktok.chunk_plan(3 * mb) == (3 * mb, 1)
    assert tiktok.chunk_plan(64 * mb) == (64 * mb, 1)
    assert tiktok.chunk_plan(100 * mb) == (32 * mb, 3)  # last chunk carries the remaining 36 MB


def test_upload_draft_sends_file_to_inbox(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x" * 1000)
    session = FakeTikTokSession()
    client = tiktok.TikTokClient("act", session)
    assert client.upload_draft(video) == "v_inbox_1"
    url, payload = session.posts[0]
    assert url == "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
    assert payload == {"source_info": {"source": "FILE_UPLOAD", "video_size": 1000, "chunk_size": 1000, "total_chunk_count": 1}}
    assert session.puts == [(1000, {"Content-Type": "video/mp4", "Content-Length": "1000", "Content-Range": "bytes 0-999/1000"})]
    assert session.headers["Authorization"] == "Bearer act"


def test_upload_draft_reports_api_errors(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x")
    with pytest.raises(tiktok.TikTokError, match="unaudited_client_can_only_post_to_private_accounts"):
        tiktok.TikTokClient("act", FakeTikTokSession("unaudited_client_can_only_post_to_private_accounts")).upload_draft(video)


def test_refresh_uses_app_credentials(monkeypatch, caplog):
    monkeypatch.setenv("TIKTOK_CLIENT_KEY", "ck")
    monkeypatch.setenv("TIKTOK_CLIENT_SECRET", "cs")
    monkeypatch.setenv("TIKTOK_REFRESH_TOKEN", "old")
    monkeypatch.delenv("TIKTOK_ACCESS_TOKEN", raising=False)
    session = FakeTikTokSession()
    client = tiktok.TikTokClient.from_env(session)
    assert session.posts[0][1] == {"client_key": "ck", "client_secret": "cs", "grant_type": "refresh_token", "refresh_token": "old"}
    assert client.session.headers["Authorization"] == "Bearer act"
    assert "rft" not in caplog.text  # a rotated token must never reach (public) logs


def test_make_renders_once_and_retries_only_the_upload(tmp_path):
    q = VideoQueue(tmp_path / "q.json")
    q.add(PLAN, status="approved")
    hf = FakeHiggsfield()
    args = argparse.Namespace(id=1)
    assert cli.cmd_make(PLATFORM, q, args, hf, FakeUploader(fail=True), fake_assemble) == 1
    assert q.get(1)["status"] == "failed" and len(q.get(1)["clips"]) == 3
    uploader = FakeUploader()
    assert cli.cmd_make(PLATFORM, q, args, hf, uploader, fake_assemble) == 0
    assert len(hf.calls) == 6  # the retry didn't pay for a second render
    assert q.get(1)["status"] == "sent" and q.get(1)["publish_id"] == "v_inbox_1"
    assert len(uploader.uploaded) == 1


def test_make_refuses_unapproved_plans(tmp_path):
    q = VideoQueue(tmp_path / "q.json")
    q.add(PLAN)
    with pytest.raises(SystemExit):
        cli.cmd_make(PLATFORM, q, argparse.Namespace(id=1), FakeHiggsfield(), FakeUploader(), fake_assemble)


def test_autopilot_plans_auto_approves_safe_ones_and_makes_one(tmp_path, monkeypatch):
    monkeypatch.setenv("TIKTOK_AUTO_APPROVE", "true")
    risky = {**PLAN, "hook": "A statistic", "fact_check": "check the 2019 figure"}
    claude = FakeClaude(message([text_block({"concepts": [PLAN, risky]})]))
    q = VideoQueue(tmp_path / "q.json")
    uploader = FakeUploader()
    args = SimpleNamespace(min_drafts=3, count=2)
    assert cli.cmd_autopilot(PLATFORM, q, args, claude, FakeHiggsfield(), uploader, fake_assemble) == 0
    assert [i["status"] for i in q.items] == ["sent", "draft"]
    request = claude.requests[0]
    assert request["output_config"]["format"]["schema"] == plans.schemas()[0]
    assert "TikTok account" in request["system"] and "3 clips of 5 seconds" in request["system"]
    assert "real stock videos from Pexels" in request["system"]  # the free default
