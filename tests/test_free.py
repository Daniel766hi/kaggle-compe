"""The free setup: a local model through Ollama, Pexels stock clips, posting to X by hand."""

import argparse
import json
import os
import shutil
import subprocess
from types import SimpleNamespace

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
from shorts import cli, plans, render
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
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.delenv("VIDEO_SOURCE", raising=False)
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
    assert llm.ollama_json("system", "request", {"type": "object"}, session) == {"ideas": []}
    body = session.bodies[0]
    assert body["model"] == "qwen3:8b" and body["format"] == {"type": "object"} and body["stream"] is False
    assert body["messages"][0] == {"role": "system", "content": "system"}


def test_ollama_not_running_is_explained():
    with pytest.raises(llm.LLMError, match="isn't running"):
        llm.ollama_json("s", "r", {}, FakeOllama(down=True))
    assert llm.available(FakeOllama(down=True)) is False


def test_ideas_use_the_local_model_and_skip_web_search(monkeypatch):
    seen = {}

    def fake_json(system, request, schema, session=None):
        seen.update(request=request, schema=schema)
        return {"ideas": [IDEA]}

    monkeypatch.setattr(llm, "ollama_json", fake_json)
    assert brain.generate_ideas("profile", 1) == [IDEA]
    assert "search the web" not in seen["request"].lower()
    assert seen["schema"] == brain.IDEAS_SCHEMA


def test_stock_plans_ask_for_search_queries():
    concepts, _ = plans.schemas()
    shot = concepts["properties"]["concepts"]["items"]["properties"]["shots"]["items"]
    assert set(shot["properties"]) == {"search_query", "on_screen_text"}
    assert "real stock videos from Pexels" in plans._system(TIKTOK, "profile")


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


def test_stock_clips_are_found_credited_and_never_reused(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "pk")
    pexels = FakePexels([clip(1, "Ana"), clip(2, "Budi", duration=2), clip(3, "Citra"), clip(4, "Ana")])
    clips = render.render_stock(STOCK_PLAN, 5, pexels)
    assert [c["video_url"] for c in clips] == ["https://p/1/hd.mp4", "https://p/3/hd.mp4", "https://p/4/hd.mp4"]
    assert pexels.calls[0] == ({"query": "cat on desk", "per_page": 15, "orientation": "portrait"}, {"Authorization": "pk"})
    assert render.credits(clips) == "Clips from Pexels: Ana, Citra"


def test_stock_falls_back_to_any_orientation_then_explains(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "pk")
    one_shot = {**STOCK_PLAN, "shots": STOCK_PLAN["shots"][:1]}
    assert render.render_stock(one_shot, 5, FakePexels([], [clip(9, "Dewi")]))[0]["credit"] == "Dewi"
    with pytest.raises(render.RenderError, match="No stock clip found for 'cat on desk'"):
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
    assert "Clips from Pexels: N1, N2, N3" in TIKTOK.done(q.get(1))


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
    assert 1.9 < info["duration"] < 2.3  # 2 shots x 1 s, not 2 x 3 s


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
