"""The free setup: a local model through Ollama, Pexels stock clips, posting to X by hand."""

import argparse
import base64
import json
import os
import shutil
import time
import subprocess
import threading
import urllib.error
import urllib.request
from types import SimpleNamespace
from urllib.parse import quote

import pytest
import requests

import llm
import local_env
from instagram_agent import __main__ as ig_main
from instagram_agent.__main__ import PLATFORM as INSTAGRAM
from office import server
from office.chat import Office, OllamaEngine
from office.desks import VideoDesk, XDesk
from office.team import build_team
from shorts import cli, images, plans, render
from tiktok_agent.__main__ import PLATFORM as TIKTOK
from x_agent import __main__ as x_cli
from x_agent import brain
from x_agent.queue import PostQueue
from x_agent.x_client import XClient

from .test_tiktok_agent import FakeUploader, fake_assemble
from .test_x_agent import IDEA, FakeSession

STOCK_PLAN = {
    "pillar": "Animals at work",
    "hook": "Cat becomes office manager",
    "shots": [
        {"search_query": "cat on desk", "on_screen_text": "New manager, day one"},
        {"search_query": "cat staring", "on_screen_text": "Performance review"},
        {"search_query": "cat sleeping keyboard", "on_screen_text": "Meeting cancelled"},
    ],
    "voiceover": "",
    "caption": "Management style: chaos. #funnyanimals",
    "sources": [],
    "fact_check": "",
}


class FakeResponse:
    def __init__(self, data, status=200):
        self.status_code, self._data, self.text = status, data, json.dumps(data)

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(self.status_code)


class FakeOllama:
    def __init__(self, *messages, down=False):
        self.messages, self.down, self.bodies = list(messages), down, []

    def post(self, url, json, timeout):
        if self.down:
            raise requests.ConnectionError("refused")
        self.bodies.append(json)
        return FakeResponse({"message": self.messages.pop(0)})

    def get(self, url, timeout):
        if self.down:
            raise requests.ConnectionError("refused")
        return FakeResponse({"models": []})


@pytest.fixture(autouse=True)
def free_setup(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("PIXABAY_API_KEY", raising=False)
    monkeypatch.delenv("STOCK_SITE", raising=False)
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.delenv("VIDEO_SOURCE", raising=False)
    for key in ("GEMINI_API_KEY", "GEMINI_MODEL", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN", "DASHSCOPE_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    for key in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"):
        monkeypatch.delenv(key, raising=False)


def test_the_free_local_model_is_the_default_without_a_claude_key(monkeypatch):
    assert llm.provider() == "ollama" and not llm.web_search_available()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    assert llm.provider() == "claude"
    monkeypatch.setenv("AI_PROVIDER", "ollama")
    assert llm.provider() == "ollama"


def test_ollama_answers_in_the_requested_json_shape():
    session = FakeOllama({"role": "assistant", "content": '<think>hmm</think>{"ideas": []}'})
    assert llm.json_answer("system", "request", {"type": "object"}, session) == {"ideas": []}
    body = session.bodies[0]
    assert body["model"] == "qwen3:8b" and body["format"] == {"type": "object"} and body["stream"] is False
    assert body["messages"][0] == {"role": "system", "content": "system"}


def test_ollama_not_running_is_explained():
    with pytest.raises(llm.LLMError, match="isn't running"):
        llm.json_answer("s", "r", {}, FakeOllama(down=True))
    assert llm.available(FakeOllama(down=True)) is False


def test_ideas_use_the_local_model_and_skip_web_search(monkeypatch):
    seen = {}

    def fake_json(system, request, schema, session=None):
        seen.update(request=request, schema=schema)
        return {"ideas": [IDEA]}

    monkeypatch.setattr(llm, "json_answer", fake_json)
    assert brain.generate_ideas("profile", 1) == [IDEA]
    assert "search the web" not in seen["request"].lower()
    assert seen["schema"] == brain.IDEAS_SCHEMA


def test_stock_plans_ask_for_search_queries():
    concepts, _ = plans.schemas()
    shot = concepts["properties"]["concepts"]["items"]["properties"]["shots"]["items"]
    assert set(shot["properties"]) == {"search_query", "on_screen_text"}
    assert "real stock videos from a free stock site" in plans._system(TIKTOK, "profile")


class FakePexels:
    def __init__(self, portrait, anything=()):
        self.portrait, self.anything, self.calls = portrait, list(anything), []

    def get(self, url, params, headers, timeout):
        self.calls.append((params, headers))
        return FakeResponse({"videos": self.portrait if params.get("orientation") == "portrait" else self.anything})


def clip(video_id, name, duration=10, files=None):
    files = files or [
        {"file_type": "video/mp4", "link": f"https://p/{video_id}/sd.mp4", "height": 960},
        {"file_type": "video/mp4", "link": f"https://p/{video_id}/hd.mp4", "height": 1920},
        {"file_type": "video/mp4", "link": f"https://p/{video_id}/4k.mp4", "height": 3840},
    ]
    return {"id": video_id, "duration": duration, "url": f"https://www.pexels.com/video/{video_id}/", "user": {"name": name}, "video_files": files}


class FirstPick:
    """Makes the random clip choice predictable in tests: always the best match."""

    def choice(self, options):
        return options[0]


def test_stock_clips_are_found_credited_and_never_reused(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "pk")
    pexels = FakePexels([clip(1, "Ana"), clip(2, "Budi", duration=2), clip(3, "Citra"), clip(4, "Ana")])
    clips = render.render_stock(STOCK_PLAN, 5, pexels, rng=FirstPick())
    assert [c["video_url"] for c in clips] == ["https://p/1/hd.mp4", "https://p/3/hd.mp4", "https://p/4/hd.mp4"]
    assert pexels.calls[0] == ({"query": "cat on desk", "per_page": 40, "orientation": "portrait"}, {"Authorization": "pk"})
    assert render.credits(clips) == "Clips from Pexels: Ana, Citra"


def test_stock_falls_back_to_any_orientation_then_explains(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "pk")
    one_shot = {**STOCK_PLAN, "shots": STOCK_PLAN["shots"][:1]}
    assert render.render_stock(one_shot, 5, FakePexels([], [clip(9, "Dewi")]))[0]["credit"] == "Dewi"
    with pytest.raises(render.RenderError, match="No unused stock clip found for 'cat on desk'"):
        render.render_stock(one_shot, 5, FakePexels([], []))
    monkeypatch.delenv("PEXELS_API_KEY")
    with pytest.raises(SystemExit):
        render.render_stock(one_shot, 5, FakePexels([]))


def test_make_uses_stock_clips_for_a_stock_plan(tmp_path, monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "pk")
    q = TIKTOK.queue(tmp_path / "t.json")
    q.add(STOCK_PLAN, status="approved")
    seen = {}

    def assemble(clips, out_dir, **options):
        seen.update(options, clips=clips)
        return out_dir / "video.mp4"

    pexels = FakePexels([clip(i, f"N{i}") for i in range(1, 4)])
    assert cli.cmd_make(TIKTOK, q, argparse.Namespace(id=1), None, FakeUploader(), assemble, pexels) == 0
    assert q.get(1)["status"] == "sent" and len(seen["clips"]) == 3
    assert seen["texts"] == ["New manager, day one", "Performance review", "Meeting cancelled"]
    credit = TIKTOK.done(q.get(1)).rsplit("Clips from Pexels: ", 1)[1]
    assert sorted(credit.split(", ")) == ["N1", "N2", "N3"]


def test_reels_credit_stock_clips_instead_of_an_ai_label():
    stock = {"caption": "Chaos. #funnyanimals", "clips": [{"credit": "Ana"}, {"credit": "Ana"}]}
    assert ig_main.final_caption(stock) == "Chaos. #funnyanimals\n\nClips from Pexels: Ana"
    ai = {"caption": "Chaos. #funnyanimals", "clips": [{"video_url": "x"}]}
    assert ig_main.final_caption(ai).endswith("Visuals made with AI.")


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_long_landscape_stock_clips_are_trimmed_and_fill_the_frame(tmp_path):
    def landscape(url, path):  # a 3 s landscape clip, longer than a shot
        subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25:duration=3", str(path)], check=True)

    video = render.assemble([{"video_url": "a"}, {"video_url": "b"}], tmp_path / "out", texts=["one", "two"],
                            seconds=1, audio=True, download=landscape)  # fmt: skip
    info = render.probe(video)
    assert (info["streams"]["video"]["width"], info["streams"]["video"]["height"]) == (1080, 1920)
    assert 1.7 < info["duration"] < 1.85  # 2 shots x 1 s minus a 0.25 s crossfade, not 2 x 3 s


def test_office_chats_through_ollama_with_tools(tmp_path):
    ollama = FakeOllama(
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "list_items", "arguments": {"status": "waiting"}}}]},
        {"role": "assistant", "content": "<think>ok</think>Nothing waiting yet."},
    )
    team = build_team(XDesk(tmp_path / "x.json"), VideoDesk(TIKTOK, tmp_path / "t.json"), VideoDesk(INSTAGRAM, tmp_path / "i.json"))
    office = Office(team, tmp_path / "data", engine=OllamaEngine(ollama))
    assert office.say("raka", "anything?") == "Nothing waiting yet."
    history = office.threads["raka"].histories["ollama"]
    assert [m["role"] for m in history] == ["user", "assistant", "tool", "assistant"]
    assert history[2] == {"role": "tool", "tool_name": "list_items", "content": '"nothing in that list"'}
    tools = ollama.bodies[0]["tools"]
    assert tools[0]["type"] == "function" and tools[0]["function"]["name"] == "list_items"
    assert ollama.bodies[0]["messages"][0]["role"] == "system"


def test_without_x_api_keys_you_post_it_yourself(tmp_path):
    team = build_team(XDesk(tmp_path / "x.json"), VideoDesk(TIKTOK, tmp_path / "t.json"), VideoDesk(INSTAGRAM, tmp_path / "i.json"))
    app = server.OfficeApp(Office(team, tmp_path / "data", engine=OllamaEngine(FakeOllama())))
    q = PostQueue(tmp_path / "x.json")
    q.add({**IDEA, "posts": ["Haze is back & so am I", "Part two"]}, status="approved")
    q.save()
    item = app.item("x", 1)
    assert item["actions"] == ["share", "mark_posted", "reject"]
    assert item["share_urls"][0] == "https://x.com/intent/post?text=Haze%20is%20back%20%26%20so%20am%20I"
    with pytest.raises(ValueError):
        app.action("x", 1, "post")  # the paid API isn't set up
    app.action("x", 1, "mark_posted")
    assert app.item("x", 1)["status"] == "posted"


def test_autopilot_without_ai_still_publishes_what_is_approved(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "available", lambda session=None: False)
    q = PostQueue(tmp_path / "q.json")
    q.add(IDEA, status="approved")
    session = FakeSession()
    args = SimpleNamespace(min_drafts=3, count=2, dry_run=False)
    assert x_cli.cmd_autopilot(q, args, XClient(session)) == 0  # not a failed run
    assert session.payloads == [{"text": "Haze is back."}]
    vq = TIKTOK.queue(tmp_path / "t.json")
    assert cli.cmd_autopilot(TIKTOK, vq, SimpleNamespace(min_drafts=3, count=2), assemble=fake_assemble) == 0


def test_keys_saved_by_setup_load_without_overriding_real_secrets(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    local_env.save("PEXELS_API_KEY", "first", env)
    local_env.save("OLLAMA_MODEL", "qwen3:4b", env)
    local_env.save("PEXELS_API_KEY", "second", env)  # replaced, not duplicated
    assert local_env.read(env) == {"OLLAMA_MODEL": "qwen3:4b", "PEXELS_API_KEY": "second"}
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.setenv("PEXELS_API_KEY", "from-github")
    local_env.load(env)
    assert os.environ["OLLAMA_MODEL"] == "qwen3:4b" and os.environ["PEXELS_API_KEY"] == "from-github"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_on_screen_text_works_with_a_colon_in_the_font_path(tmp_path, monkeypatch):
    # Windows paths look like C:/Windows/Fonts/arialbd.ttf; ffmpeg filters need that colon escaped.
    fonts = tmp_path / "C:" / "Fonts"
    fonts.mkdir(parents=True)
    source = next((f for f in render.FONTS if os.path.exists(f)), None)
    if source is None:
        pytest.skip("no font installed")
    shutil.copy(source, fonts / "font.ttf")
    monkeypatch.setenv("VIDEO_FONT", str(fonts / "font.ttf"))

    def short(url, path):
        subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x480:rate=25:duration=1", str(path)], check=True)

    video = render.assemble([{"video_url": "a"}], tmp_path / "out", texts=["hello"], seconds=1, audio=True, download=short)
    assert render.probe(video)["streams"]["video"]["height"] == 1920


class FakePixabay:
    def __init__(self, hits):
        self.hits, self.calls = hits, []

    def get(self, url, params, headers, timeout):
        self.calls.append((url, params, headers))
        return FakeResponse({"total": len(self.hits), "hits": self.hits})


def pixabay_hit(hit_id, user, duration=12):
    return {
        "id": hit_id, "duration": duration, "user": user, "pageURL": f"https://pixabay.com/videos/{hit_id}/",
        "videos": {"large": {"url": f"https://cdn/{hit_id}/4k.mp4", "height": 2160},
                   "medium": {"url": f"https://cdn/{hit_id}/1080.mp4", "height": 1080},
                   "small": {"url": f"https://cdn/{hit_id}/720.mp4", "height": 720}},
    }  # fmt: skip


def test_pixabay_is_used_when_its_key_is_set(monkeypatch):
    monkeypatch.setenv("PIXABAY_API_KEY", "px")
    monkeypatch.setenv("PEXELS_API_KEY", "pk")  # Pixabay wins: Pexels has paused new keys
    assert render.stock_site() == "pixabay"
    pixabay = FakePixabay([pixabay_hit(1, "goatlover", duration=3), pixabay_hit(2, "catcam"), pixabay_hit(3, "dogday")])
    clips = render.render_stock({**STOCK_PLAN, "shots": STOCK_PLAN["shots"][:2]}, 5, pixabay, rng=FirstPick())
    assert [c["video_url"] for c in clips] == ["https://cdn/2/1080.mp4", "https://cdn/3/1080.mp4"]  # 1 is too short
    url, params, headers = pixabay.calls[0]
    assert url == "https://pixabay.com/api/videos/" and params["key"] == "px" and params["q"] == "cat on desk"
    assert "python-requests" not in headers["User-Agent"]  # Cloudflare challenges the default one
    assert render.credits(clips) == "Clips from Pixabay: catcam, dogday"


def test_without_any_stock_key_the_message_points_to_pixabay(monkeypatch):
    monkeypatch.delenv("PIXABAY_API_KEY", raising=False)
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    monkeypatch.delenv("STOCK_SITE", raising=False)
    with pytest.raises(SystemExit, match="PIXABAY_API_KEY"):
        render.stock_site()


def test_no_two_videos_show_the_same_clip(tmp_path, monkeypatch):
    """The bug: every video showed the same cat, because each video started from the top result."""
    monkeypatch.setenv("PIXABAY_API_KEY", "px")
    q = TIKTOK.queue(tmp_path / "t.json")
    for _ in range(3):
        q.add({**STOCK_PLAN, "shots": [{"search_query": "cat", "on_screen_text": "x"}] * 3}, status="approved")
    pixabay = FakePixabay([pixabay_hit(i, f"u{i}") for i in range(1, 11)])  # the same results every search
    for item_id in (1, 2, 3):
        assert cli.cmd_make(TIKTOK, q, argparse.Namespace(id=item_id), None, FakeUploader(), fake_assemble, pixabay) == 0
    pages = [c["source"] for it in q.items for c in it["clips"]]
    assert len(pages) == 9 and len(set(pages)) == 9


def test_random_picks_vary_between_runs(monkeypatch):
    monkeypatch.setenv("PIXABAY_API_KEY", "px")
    hits = [pixabay_hit(i, f"u{i}") for i in range(1, 30)]
    one_shot = {**STOCK_PLAN, "shots": STOCK_PLAN["shots"][:1]}
    picks = {render.render_stock(one_shot, 5, FakePixabay(hits))[0]["source"] for _ in range(20)}
    assert len(picks) > 3  # not the top result every time
    assert picks <= {f"https://pixabay.com/videos/{i}/" for i in range(1, render.PICK_FROM + 1)}  # but a good one


def test_new_clips_replaces_the_footage_for_free(tmp_path, monkeypatch):
    monkeypatch.setenv("PIXABAY_API_KEY", "px")
    q = TIKTOK.queue(tmp_path / "t.json")
    q.add(STOCK_PLAN, status="approved")
    pixabay = FakePixabay([pixabay_hit(i, f"u{i}") for i in range(1, 20)])
    cli.cmd_make(TIKTOK, q, argparse.Namespace(id=1, no_upload=True), None, None, fake_assemble, pixabay)
    first = {c["source"] for c in q.get(1)["clips"]}
    cli.cmd_make(TIKTOK, q, argparse.Namespace(id=1, no_upload=True, new_clips=True), None, None, fake_assemble, pixabay)
    second = {c["source"] for c in q.get(1)["clips"]}
    assert len(second) == 3 and not first & second


def test_plans_ask_for_different_animals_than_recent_videos(monkeypatch):
    seen = {}

    def fake_json(system, request, schema, session=None):
        seen["request"] = request
        return {"concepts": []}

    monkeypatch.setattr(llm, "json_answer", fake_json)
    items = [{"shots": [{"search_query": "cat on desk"}, {"search_query": "cat staring"}]}]
    plans.generate(TIKTOK, "profile", 2, searches=plans.recent_searches(items))
    assert "different animal" in seen["request"]
    assert "- cat on desk\n- cat staring" in seen["request"]
    assert "not only cats" in plans._system(TIKTOK, "profile")


def test_office_new_clips_button_swaps_the_footage(tmp_path, monkeypatch):
    monkeypatch.setenv("PIXABAY_API_KEY", "px")
    pixabay = FakePixabay([pixabay_hit(i, f"u{i}") for i in range(1, 20)])
    tiktok = VideoDesk(TIKTOK, tmp_path / "t.json", assemble=fake_assemble, stock=pixabay)
    team = build_team(XDesk(tmp_path / "x.json"), tiktok, VideoDesk(INSTAGRAM, tmp_path / "i.json"))
    app = server.OfficeApp(Office(team, tmp_path / "data", engine=OllamaEngine(FakeOllama())))
    q = TIKTOK.queue(tmp_path / "t.json")
    q.add(STOCK_PLAN, status="approved")
    q.save()
    app.action("tiktok", 1, "render")
    for _ in range(200):
        if not app.jobs:
            break
        time.sleep(0.02)
    first = {c["source"] for c in tiktok.item(1)["clips"]}
    assert app.item("tiktok", 1)["actions"] == ["publish", "new_clips", "reject"]
    app.action("tiktok", 1, "new_clips")
    for _ in range(200):
        if not app.jobs:
            break
        time.sleep(0.02)
    assert not first & {c["source"] for c in tiktok.item(1)["clips"]}
    assert any("New clips are in" in e["text"] for e in app.office.threads["sari"].feed)


def test_every_video_gets_its_own_original_music(tmp_path):
    from shorts import music

    a, b, again = (music.make_track(tmp_path / f"{n}.wav", 6, seed) for n, seed in (("a", 1), ("b", 2), ("again", 1)))
    assert a.read_bytes() == again.read_bytes()  # the same video always gets the same tune
    assert a.read_bytes() != b.read_bytes()  # different videos get different tunes
    info = render.probe(a) if shutil.which("ffprobe") else {"duration": 6.5}
    assert 6 <= info["duration"] <= 7


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_videos_crossfade_and_carry_music_by_default(tmp_path):
    def clip(url, path):
        subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25", "-t", "4", str(path)], check=True)

    video = render.assemble([{"video_url": "a"}, {"video_url": "b"}, {"video_url": "c"}], tmp_path / "out",
                            texts=["one", "two", "three"], seconds=2, audio=True, seed=7, download=clip)  # fmt: skip
    info = render.probe(video)
    assert (tmp_path / "out" / "music.wav").exists()  # no tracks given: an original tune was made
    assert info["streams"]["audio"]["codec_name"] == "aac"
    assert 5.1 < info["duration"] < 5.3  # 3 x 2 s minus two 0.4 s crossfades
    volume = subprocess.run(["ffmpeg", "-i", str(video), "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
    assert float(volume.stderr.split("mean_volume: ")[1].split(" dB")[0]) > -40  # actually audible, not silence


def test_balanced_caption_lines():
    assert render.balanced_lines("New manager, day one") == ["New manager,", "day one"]
    assert render.balanced_lines("Meeting cancelled") == ["Meeting cancelled"]


UPLOAD_PLAN = {
    **STOCK_PLAN,
    "shots": [
        {"video_prompt": "A tabby cat in a tiny tie sits at an office desk, vertical 9:16, photorealistic, 5 seconds",
         "on_screen_text": "New manager, day one"},
        {"video_prompt": "The same tabby cat stares at a laptop, vertical 9:16, photorealistic, 5 seconds",
         "on_screen_text": "Performance review"},
        {"video_prompt": "The same tabby cat falls asleep on the keyboard, vertical 9:16, photorealistic, 5 seconds",
         "on_screen_text": "Meeting cancelled"},
    ],
}  # fmt: skip


def test_upload_plans_ask_for_video_prompts():
    assert set(plans.schemas("upload")[0]["properties"]["concepts"]["items"]["properties"]["shots"]["items"]["required"]) == {
        "video_prompt", "on_screen_text"}  # fmt: skip


def test_clips_you_add_are_kept_per_shot_and_replaced(tmp_path):
    folder = tmp_path / "uploads"
    assert render.uploaded(folder, 3) == [None, None, None]
    render.save_upload(folder, 2, b"one", "Dreamina clip.MP4")
    render.save_upload(folder, 2, b"two", "better.mov")  # replaces the first
    found = render.uploaded(folder, 3)
    assert found[0] is None and found[1].name == "shot_2.mov" and found[1].read_bytes() == b"two"
    assert not (folder / "shot_2.mp4").exists()
    with pytest.raises(ValueError, match="video file"):
        render.save_upload(folder, 1, b"x", "photo.png")
    with pytest.raises(ValueError, match="empty"):
        render.save_upload(folder, 1, b"", "clip.mp4")


def test_make_waits_for_your_clips_then_uses_them(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    q = TIKTOK.queue(tmp_path / "t.json")
    q.add(UPLOAD_PLAN, status="approved")
    seen = {}

    def assemble(clips, out_dir, **options):
        seen.update(options, clips=clips)
        return out_dir / "video.mp4"

    args = argparse.Namespace(id=1)
    folder = cli.upload_folder(TIKTOK, 1)
    render.save_upload(folder, 1, b"a", "a.mp4")
    assert cli.cmd_make(TIKTOK, q, args, None, FakeUploader(), assemble) == 1
    assert q.get(1)["status"] == "approved" and "shot 2, 3" in q.get(1)["error"] and not seen
    render.save_upload(folder, 2, b"b", "b.mp4")
    render.save_upload(folder, 3, b"c", "c.webm")
    assert cli.cmd_make(TIKTOK, q, args, None, FakeUploader(), assemble) == 0
    assert q.get(1)["status"] == "sent" and not q.get(1)["error"]
    assert [c["source"] for c in seen["clips"]] == ["upload:shot_1.mp4", "upload:shot_2.mp4", "upload:shot_3.webm"]
    assert seen["texts"][0] == "New manager, day one"
    assert "Visuals made with AI." in ig_main.final_caption(q.get(1))


def test_autopilot_skips_plans_still_waiting_for_your_clips(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(llm, "available", lambda: False)
    q = TIKTOK.queue(tmp_path / "t.json")
    q.add(UPLOAD_PLAN, status="approved")
    args = argparse.Namespace(min_drafts=0, count=1)
    assert cli.cmd_autopilot(TIKTOK, q, args, client=FakeUploader(), assemble=fake_assemble) == 0
    assert q.get(1)["status"] == "approved" and not q.get(1).get("error")


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_office_add_clip_buttons_then_render(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tiktok = VideoDesk(TIKTOK, tmp_path / "t.json", client=FakeUploader())
    team = build_team(XDesk(tmp_path / "x.json"), tiktok, VideoDesk(INSTAGRAM, tmp_path / "i.json"))
    app = server.OfficeApp(Office(team, tmp_path / "data", engine=OllamaEngine(FakeOllama())))
    q = TIKTOK.queue(tmp_path / "t.json")
    q.add(UPLOAD_PLAN)
    q.save()
    assert app.item("tiktok", 1)["uploads"] == [False, False, False]
    app.action("tiktok", 1, "approve")
    assert app.item("tiktok", 1)["actions"] == ["reject"]  # nothing to render until your clips are in
    app.office.checkin()
    assert "waiting for your clips" in app.office.threads["sari"].feed[-1]["text"]

    httpd = server.serve(app, port=0, checkin_minutes=60)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        for shot in (1, 2, 3):
            path = tmp_path / f"made_{shot}.mp4"
            subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=360x640:rate=25:duration=2",
                            str(path)], check=True)  # fmt: skip
            req = urllib.request.Request(f"{base}/api/upload/tiktok/1/{shot}", data=path.read_bytes(), method="POST",
                                         headers={"X-Office": "1", "X-Filename": quote(f"Dreamina {shot}.mp4")})  # fmt: skip
            assert urllib.request.urlopen(req).status == 200
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(urllib.request.Request(f"{base}/api/upload/tiktok/1/4", data=b"x", method="POST",
                                                          headers={"X-Office": "1", "X-Filename": "a.mp4"}))  # fmt: skip
        assert e.value.code == 400
    finally:
        httpd.shutdown()
    item = app.item("tiktok", 1)
    assert item["uploads"] == [True, True, True] and item["actions"] == ["render", "publish", "reject"]
    assert any("All clips are in" in e["text"] for e in app.office.threads["sari"].feed)
    app.action("tiktok", 1, "render")
    for _ in range(1000):
        if not app.jobs:
            break
        time.sleep(0.05)
    item = app.item("tiktok", 1)
    assert item["status"] == "rendered" and item.get("video"), item
    assert item["actions"] == ["render", "publish", "reject"]  # replace a clip and render again


# --- Gemini: the free cloud brain -------------------------------------------------------------


class FakeGemini:
    """Stands in for requests against Gemini's OpenAI-compatible API."""

    def __init__(self, *messages, statuses=()):
        self.messages, self.statuses, self.calls = list(messages), list(statuses), []

    def post(self, url, json, headers, timeout):
        self.calls.append({"url": url, "body": json, "headers": headers})
        status = self.statuses.pop(0) if self.statuses else 200
        if status != 200:
            return FakeResponse({"error": {"message": "slow down"}}, status)
        return FakeResponse({"choices": [{"message": self.messages.pop(0)}]})


def test_a_gemini_key_makes_gemini_the_free_brain(monkeypatch):
    assert llm.provider() == "ollama"
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    assert llm.provider() == "gemini" and llm.available()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a-key")
    assert llm.provider() == "claude"
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    assert llm.provider() == "gemini"


def test_gemini_answers_in_json_and_waits_out_its_rate_limit(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    session = FakeGemini({"role": "assistant", "content": '```json\n{"ideas": []}\n```'}, statuses=[429])
    schema = {"type": "object", "properties": {"ideas": {"type": "array"}}, "required": ["ideas"], "additionalProperties": False}
    assert llm.json_answer("system", "request", schema, session) == {"ideas": []}
    call = session.calls[-1]
    assert len(session.calls) == 2 and call["url"].endswith("/v1beta/openai/chat/completions")
    assert call["headers"]["Authorization"] == "Bearer g-key" and call["body"]["model"] == "gemini-flash-latest"
    sent = call["body"]["response_format"]["json_schema"]["schema"]
    assert "additionalProperties" not in sent and sent["required"] == ["ideas"]


def test_gemini_explains_a_used_up_free_limit(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    session = FakeGemini(statuses=[429, 429, 429, 429])
    with pytest.raises(llm.LLMError, match="free limit"):
        llm.gemini_chat([{"role": "user", "content": "hi"}], session=session, sleep=lambda s: None)


def test_office_chats_through_gemini_with_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    call = {"id": "fc_1", "type": "function", "function": {"name": "list_items", "arguments": '{"status": "waiting"}'},
            "extra_content": {"google": {"thought_signature": "sig"}}}  # fmt: skip
    session = FakeGemini({"role": "assistant", "content": None, "tool_calls": [call]},
                         {"role": "assistant", "content": "Nothing waiting yet."})  # fmt: skip
    team = build_team(XDesk(tmp_path / "x.json"), VideoDesk(TIKTOK, tmp_path / "t.json"), VideoDesk(INSTAGRAM, tmp_path / "i.json"))
    office = Office(team, tmp_path / "data", engine=OllamaEngine(session))
    assert office.engine.name == "gemini"
    assert office.say("raka", "anything waiting?") == "Nothing waiting yet."
    history = office.threads["raka"].histories["gemini"]
    assert history[1]["tool_calls"][0]["extra_content"] == {"google": {"thought_signature": "sig"}}  # sent back as is
    assert history[2]["role"] == "tool" and history[2]["tool_call_id"] == "fc_1"
    second = session.calls[1]["body"]
    assert [m["role"] for m in second["messages"]] == ["system", "user", "assistant", "tool"]


# --- AI pictures: free FLUX images on Cloudflare, brought to life ----------------------------

PICTURE_PLAN = {
    **STOCK_PLAN,
    "shots": [
        {"image_prompt": "A chubby orange tabby cat wearing a tiny blue necktie sits behind a desk",
         "action": "the cat squints at the camera", "camera": "zoom_in", "on_screen_text": "New manager, day one"},
        {"image_prompt": "A chubby orange tabby cat wearing a tiny blue necktie stares at a laptop",
         "action": "the cat leans closer", "camera": "pan_right", "on_screen_text": "Performance review"},
        {"image_prompt": "A chubby orange tabby cat wearing a tiny blue necktie asleep on a keyboard",
         "action": "the cat's ear twitches", "camera": "zoom_out", "on_screen_text": "Meeting cancelled"},
    ],
}  # fmt: skip


def picture_bytes(tmp_path):
    path = tmp_path / "drawn.png"
    if not path.exists():
        subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=768x1344",
                        "-frames:v", "1", str(path)], check=True)  # fmt: skip
    return path.read_bytes()


class FakePictures:
    model = "@cf/black-forest-labs/flux-2-klein-4b"

    def __init__(self, data):
        self.data, self.calls = data, []

    def generate(self, prompt, reference=None):
        self.calls.append((prompt, reference))
        return self.data


class FakeCloudflare:
    def __init__(self, status=200, text=None):
        self.status, self.text, self.calls = status, text, []

    def post(self, url, headers, timeout, files=None, json=None):
        self.calls.append({"url": url, "headers": headers, "files": files, "json": json})
        if self.status != 200:
            resp = FakeResponse({}, self.status)
            resp.text = self.text or ""
            return resp
        return FakeResponse({"result": {"image": base64.b64encode(b"PNGDATA").decode()}, "success": True})


def test_cloudflare_draws_a_vertical_picture_with_a_reference():
    session = FakeCloudflare()
    pictures = images.CloudflareImages("acc", "tok", session)
    assert pictures.generate("a goat in a hard hat", reference=b"REF") == b"PNGDATA"
    call = session.calls[0]
    assert call["url"] == "https://api.cloudflare.com/client/v4/accounts/acc/ai/run/@cf/black-forest-labs/flux-2-klein-4b"
    assert call["headers"]["Authorization"] == "Bearer tok"
    assert call["files"]["prompt"] == (None, "a goat in a hard hat") and call["files"]["width"] == (None, "768")
    assert call["files"]["input_image_0"][1] == b"REF"


def test_cloudflare_explains_the_daily_free_limit():
    session = FakeCloudflare(400, '{"errors":[{"code":4006,"message":"you have used up your daily free allocation"}]}')
    with pytest.raises(render.RenderError, match="07:00 WIB"):
        images.CloudflareImages("acc", "tok", session).generate("a duck")


def test_pictures_are_the_default_once_cloudflare_is_set_up(monkeypatch):
    assert plans.video_source() == "stock"
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acc")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")
    assert plans.video_source() == "images"
    shot = plans.schemas()[0]["properties"]["concepts"]["items"]["properties"]["shots"]["items"]
    assert shot["required"] == ["image_prompt", "action", "camera", "on_screen_text"]
    assert "word for word" in plans._system(TIKTOK, "profile")


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_pictures_become_smooth_moving_shots_of_the_same_animal(tmp_path):
    fake = FakePictures(picture_bytes(tmp_path))
    clips = images.render_pictures(PICTURE_PLAN, 2, tmp_path / "out", fake)
    assert fake.calls[0][1] is None and fake.calls[1][1] and fake.calls[1][1] == fake.calls[2][1]  # shot 1 is the model
    assert [c["source"] for c in clips] == ["ai-picture:picture_1.png", "ai-picture:picture_2.png", "ai-picture:picture_3.png"]
    info = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height,nb_frames",
                           "-of", "csv=p=0", clips[0]["video_url"]], capture_output=True, text=True).stdout.strip()  # fmt: skip
    assert info == f"1080,1920,{int(round((2 + render.FADE) * 30))}"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_wan_animates_the_pictures_and_falls_back_to_camera_moves(tmp_path, monkeypatch):
    class BrokeWan:
        def __init__(self):
            self.calls = 0

        def animate(self, picture, prompt, seconds):
            self.calls += 1
            raise render.RenderError("free quota used up")

    wan = BrokeWan()
    clips = images.render_pictures(PICTURE_PLAN, 1, tmp_path / "out", FakePictures(picture_bytes(tmp_path)), wan=wan)
    assert wan.calls == 1 and all(c["source"].startswith("ai-picture:") for c in clips)

    class GoodWan:
        def animate(self, picture, prompt, seconds):
            return str(tmp_path / "out" / "moving_1.mp4")  # any finished clip

    clips = images.render_pictures(PICTURE_PLAN, 1, tmp_path / "again", FakePictures(picture_bytes(tmp_path)), wan=GoodWan())
    assert [c["source"] for c in clips] == ["wan:picture_1.png", "wan:picture_2.png", "wan:picture_3.png"]


def test_wan_task_is_created_and_polled():
    class FakeDashScope:
        def __init__(self):
            self.posts, self.gets = [], 0

        def post(self, url, headers, json, timeout):
            self.posts.append((url, headers, json))
            return FakeResponse({"output": {"task_id": "t1", "task_status": "PENDING"}})

        def get(self, url, headers, timeout):
            self.gets += 1
            status = "SUCCEEDED" if self.gets > 1 else "RUNNING"
            return FakeResponse({"output": {"task_status": status, "video_url": "https://wan.example/clip.mp4"}})

    session = FakeDashScope()
    wan = images.Wan("d-key", session, sleep=lambda s: None)
    assert wan.animate(b"PNG", "the cat squints", 5) == "https://wan.example/clip.mp4"
    url, headers, body = session.posts[0]
    assert url.endswith("/api/v1/services/aigc/video-generation/video-synthesis") and headers["X-DashScope-Async"] == "enable"
    assert body["input"]["img_url"].startswith("data:image/png;base64,") and body["parameters"]["duration"] == 5


def test_make_draws_a_picture_plan_and_new_pictures_are_free(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    q = TIKTOK.queue(tmp_path / "t.json")
    q.add(PICTURE_PLAN, status="approved")
    drawn = []

    def render_pictures(item, seconds, folder, pictures):
        drawn.append(folder)
        return [{"video_url": f"{folder}/moving_{n}.mp4", "source": f"ai-picture:picture_{n}.png"} for n in (1, 2, 3)]

    monkeypatch.setattr(images, "render_pictures", render_pictures)
    seen = {}

    def assemble(clips, out_dir, **options):
        seen.update(options, clips=clips)
        return out_dir / "video.mp4"

    args = argparse.Namespace(id=1, no_upload=True)
    assert cli.cmd_make(TIKTOK, q, args, None, FakeUploader(), assemble) == 0
    assert drawn == [cli.Path("build/tiktok/1/pictures")] and q.get(1)["status"] == "rendered"
    assert server._actions("tiktok", q.get(1)) == ["publish", "new_clips", "reject"]
    cli.cmd_make(TIKTOK, q, argparse.Namespace(id=1, no_upload=True, new_clips=True), None, FakeUploader(), assemble)
    assert len(drawn) == 2  # drawn again, for free
    assert "Visuals made with AI." in ig_main.final_caption(q.get(1))
