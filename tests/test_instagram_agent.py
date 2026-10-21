import argparse
import json
import shutil
import subprocess

import pytest

from instagram_agent import __main__ as ig_main
from instagram_agent import instagram
from instagram_agent.__main__ import PLATFORM
from shorts import cli, plans, render
from shorts.plans import VideoQueue

from .test_tiktok_agent import PLAN, SHOT, FakeHiggsfield
from .test_x_agent import FakeClaude, message, text_block

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")


class FakeResponse:
    def __init__(self, status, data):
        self.status_code, self._data, self.text = status, data, json.dumps(data)

    def json(self):
        return self._data


class FakeGraph:
    """Answers the Graph API calls of one Reel upload; records every request."""

    def __init__(self, used=0, processing=("IN_PROGRESS", "FINISHED"), permalink_fails=False):
        self.calls, self.used = [], used
        self.processing, self.permalink_fails = list(processing), permalink_fails

    def get(self, url, params, timeout):
        self.calls.append(("GET", url, params))
        if url.endswith("/content_publishing_limit"):
            return FakeResponse(200, {"data": [{"config": {"quota_total": 100}, "quota_usage": self.used}]})
        if url.endswith("/c1"):
            code = self.processing.pop(0)
            return FakeResponse(200, {"status_code": code, "status": f"{code}: details"})
        if url.endswith("/m1"):
            if self.permalink_fails:
                return FakeResponse(500, {"error": {"message": "temporary"}})
            return FakeResponse(200, {"permalink": "https://www.instagram.com/reel/abc/"})
        if url.endswith("/oauth/access_token"):
            return FakeResponse(200, {"access_token": "long-user"})
        if url.endswith("/me/accounts"):
            return FakeResponse(200, {"data": [
                {"name": "No IG page", "access_token": "x"},
                {"name": "My Page", "access_token": "page-token", "instagram_business_account": {"id": "1784", "username": "me"}},
            ]})  # fmt: skip
        raise AssertionError(url)

    def post(self, url, data=None, headers=None, timeout=None):
        self.calls.append(("POST", url, data if headers is None else (len(data), headers)))
        if url.endswith("/media"):
            return FakeResponse(200, {"id": "c1"})
        if "rupload.facebook.com" in url:
            return FakeResponse(200, {"success": True})
        if url.endswith("/media_publish"):
            return FakeResponse(200, {"id": "m1"})
        raise AssertionError(url)


def client(graph, sleeps=None):
    return instagram.InstagramClient("1784", "tok", graph, sleep=(sleeps.append if sleeps is not None else lambda s: None))


def test_publish_reel_uploads_waits_and_publishes(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"v" * 500)
    graph, sleeps = FakeGraph(), []
    result = client(graph, sleeps).publish_reel(video, "Caption #indonesia")
    assert result == {"media_id": "m1", "url": "https://www.instagram.com/reel/abc/"}
    create = graph.calls[1]
    assert create[1] == f"{instagram.GRAPH}/1784/media"
    assert create[2] == {
        "media_type": "REELS", "upload_type": "resumable", "caption": "Caption #indonesia",
        "share_to_feed": "true", "access_token": "tok",
    }  # fmt: skip
    upload = graph.calls[2]
    assert upload[1] == f"{instagram.RUPLOAD}/c1"
    assert upload[2] == (500, {"Authorization": "OAuth tok", "offset": "0", "file_size": "500"})
    assert sleeps == [instagram.POLL_S]  # waited once while IN_PROGRESS
    assert graph.calls[-2][1].endswith("/1784/media_publish") and graph.calls[-2][2]["creation_id"] == "c1"


def test_publish_stops_at_the_daily_limit(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"v")
    graph = FakeGraph(used=100)
    with pytest.raises(instagram.InstagramError, match="limit reached"):
        client(graph).publish_reel(video, "c")
    assert len(graph.calls) == 1  # nothing was created


def test_processing_error_is_reported(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"v")
    with pytest.raises(instagram.InstagramError, match="ERROR: details"):
        client(FakeGraph(processing=("ERROR",))).publish_reel(video, "c")


def test_live_reel_is_not_failed_by_a_missing_link(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"v")
    assert client(FakeGraph(permalink_fails=True)).publish_reel(video, "c") == {"media_id": "m1", "url": ""}


def test_connect_finds_the_linked_instagram_account():
    graph = FakeGraph()
    accounts = instagram.connect("app", "secret", "short", graph)
    assert accounts == [{"page": "My Page", "username": "me", "user_id": "1784", "access_token": "page-token"}]
    assert graph.calls[0][2] == {"grant_type": "fb_exchange_token", "client_id": "app", "client_secret": "secret", "fb_exchange_token": "short"}
    assert graph.calls[1][2]["access_token"] == "long-user"


def test_caption_gets_an_ai_disclosure_once():
    assert ig_main.caption_with_disclosure("Haze season #indonesia") == "Haze season #indonesia\n\nVisuals made with AI."
    assert ig_main.caption_with_disclosure("AI-generated visuals #haze") == "AI-generated visuals #haze"
    assert ig_main.caption_with_disclosure("Trip to Bali, said no one") .endswith("Visuals made with AI.")


def test_instagram_plan_limits():
    wordy = {**PLAN, "shots": [{**SHOT, "on_screen_text": "one two three four five six seven eight nine ten eleven twelve thirteen"}, SHOT, SHOT]}
    assert plans.problems(PLATFORM, wordy) == ["shot 1 on-screen text is 13 words (12 fit on screen)"]
    tags = {**PLAN, "caption": " ".join(f"#t{i}" for i in range(31))}
    assert plans.problems(PLATFORM, tags) == ["caption has 31 hashtags (limit 30)"]


def test_make_burns_text_adds_audio_and_publishes(tmp_path, monkeypatch):
    monkeypatch.setenv("INSTAGRAM_MUSIC", str(tmp_path / "no-music-here"))
    q = VideoQueue(tmp_path / "q.json")
    q.add(PLAN, status="approved")
    seen = {}

    def assemble(clips, out_dir, **options):
        seen.update(options)
        return out_dir / "video.mp4"

    class FakeClient:
        def publish_reel(self, video, caption):
            seen["caption"] = caption
            return {"media_id": "m1", "url": "https://www.instagram.com/reel/abc/"}

    monkeypatch.setattr(render, "probe", lambda path: {"duration": 15.0, "streams": {"audio": {"codec_name": "aac"}}})
    assert cli.cmd_make(PLATFORM, q, argparse.Namespace(id=1), FakeHiggsfield(), FakeClient(), assemble) == 0
    assert seen["texts"] == ["Haze is back"] * 3 and seen["seconds"] == 5
    assert seen["audio"] is True and seen["music"] is None
    assert seen["caption"].endswith("Visuals made with AI.")
    assert q.get(1)["status"] == "posted" and q.get(1)["url"] == "https://www.instagram.com/reel/abc/"


def test_make_refuses_videos_instagram_would_reject(tmp_path, monkeypatch):
    q = VideoQueue(tmp_path / "q.json")
    q.add(PLAN, status="approved")
    monkeypatch.setattr(render, "probe", lambda path: {"duration": 2.0, "streams": {"audio": {"codec_name": "aac"}}})
    code = cli.cmd_make(PLATFORM, q, argparse.Namespace(id=1), FakeHiggsfield(), object(), lambda c, d, **o: d / "v.mp4")
    assert code == 1 and "3 s to 15 min" in q.get(1)["error"]


def test_autopilot_prompts_for_burned_in_text(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "load_profile", lambda: "profile")
    claude = FakeClaude(message([text_block({"concepts": [PLAN]})]))
    q = VideoQueue(tmp_path / "q.json")
    assert cli.cmd_autopilot(PLATFORM, q, argparse.Namespace(min_drafts=3, count=1), claude) == 0
    system = claude.requests[0]["system"]
    assert "Instagram Reels account" in system and "12 words per shot" in system
    assert [i["status"] for i in q.items] == ["draft"]  # nothing is published without approval


def test_pick_music_rotates_through_a_folder(tmp_path):
    (tmp_path / "b.mp3").write_bytes(b"")
    (tmp_path / "a.m4a").write_bytes(b"")
    (tmp_path / "notes.txt").write_text("")
    assert render.pick_music(tmp_path, 1).name == "b.mp3"
    assert render.pick_music(tmp_path, 2).name == "a.m4a"
    assert render.pick_music(tmp_path / "missing", 1) is None


def _test_clip(url, path):  # stands in for downloading: a 1 s test pattern of another size
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x480:rate=24:duration=1", str(path)], check=True)


@needs_ffmpeg
@pytest.mark.parametrize("with_music", [False, True])
def test_assemble_makes_a_reel_instagram_accepts(tmp_path, with_music):
    music = None
    if with_music:
        music = tmp_path / "music.mp3"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5", str(music)], check=True)
    clips = [{"video_url": "a"}, {"video_url": "b"}]
    texts = ["Why does the haze come back every year?", "It's not only the weather"]
    video = render.assemble(clips, tmp_path / "out", texts=texts, seconds=1, audio=True, music=music, download=_test_clip)
    info = render.probe(video)
    assert info["streams"]["video"]["codec_name"] == "h264"
    assert (info["streams"]["video"]["width"], info["streams"]["video"]["height"]) == (1080, 1920)
    assert info["streams"]["audio"]["codec_name"] == "aac" and info["streams"]["audio"]["sample_rate"] == "48000"
    assert 1.9 < info["duration"] < 2.2  # looped music is cut to the video's length
    assert (tmp_path / "out" / "text_1.txt").read_text() == "Why does the haze\ncome back every\nyear?"
