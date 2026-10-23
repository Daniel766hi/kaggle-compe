import json
import threading
import time
import urllib.error
import urllib.request
from types import SimpleNamespace

import pytest
from anthropic.types.beta import BetaTextBlock, BetaToolUseBlock

from instagram_agent.__main__ import PLATFORM as INSTAGRAM
from office import chat, server
from office.chat import Office
from office.desks import VideoDesk, XDesk
from office.team import build_team
from tiktok_agent.__main__ import PLATFORM as TIKTOK
from x_agent.queue import PostQueue
from x_agent.x_client import XClient

from .test_tiktok_agent import PLAN, FakeHiggsfield, FakeUploader, fake_assemble
from .test_x_agent import IDEA, FakeSession


class FakeClaude:
    """Stands in for anthropic.Anthropic() in the office: replies come from a script."""

    def __init__(self, *replies):
        self.replies, self.requests = list(replies), []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **params):
        self.requests.append(json.loads(json.dumps(params["messages"])))  # a snapshot, as sent
        self.last_params = params
        return self.replies.pop(0)


def say(text):
    return SimpleNamespace(stop_reason="end_turn", content=[BetaTextBlock(type="text", text=text)])


def use(name, args, tool_id="t1", text=None):
    content = [BetaTextBlock(type="text", text=text)] if text else []
    content.append(BetaToolUseBlock(type="tool_use", id=tool_id, name=name, input=args))
    return SimpleNamespace(stop_reason="tool_use", content=content)


@pytest.fixture
def office(tmp_path):
    def build(*replies, x_session=None):
        x_desk = XDesk(tmp_path / "x.json", x_client=XClient(x_session or FakeSession()))
        tiktok = VideoDesk(TIKTOK, tmp_path / "t.json", hf=FakeHiggsfield(), client=FakeUploader(), assemble=fake_assemble)
        insta = VideoDesk(INSTAGRAM, tmp_path / "i.json")
        claude = FakeClaude(*replies)
        return Office(build_team(x_desk, tiktok, insta), tmp_path / "data", claude), claude

    return build


def test_agent_uses_its_tools_and_replies(office):
    o, claude = office(use("list_items", {"status": "waiting"}, text="Let me look."), say("You have 1 draft: [[x:1]]"))
    q = PostQueue(o.team["raka"].desk.queue_path)
    q.add(IDEA)
    q.save()
    assert o.say("raka", "What's waiting?") == "Let me look.\n\nYou have 1 draft: [[x:1]]"
    feed = o.threads["raka"].feed
    assert [(e["from"], e["text"]) for e in feed] == [
        ("you", "What's waiting?"), ("agent", "Let me look."), ("agent", "You have 1 draft: [[x:1]]"),
    ]  # fmt: skip
    history = o.threads["raka"].history
    assert [m["role"] for m in history] == ["user", "assistant", "user", "assistant"]
    result = history[2]["content"][0]
    assert result["type"] == "tool_result" and json.loads(result["content"])[0]["hook"] == "Haze season starts"
    params = claude.last_params
    assert params["model"] == "claude-opus-5-5" and params["fallbacks"] == "default"
    assert {t["name"] for t in params["tools"]} == {"list_items", "show_item", "create_drafts", "revise_item", "reject_item"}
    assert "cannot approve or publish" in params["system"][0]["text"]


def test_agents_have_no_tool_that_publishes(office):
    o, _ = office()
    names = {t["name"] for a in o.team.values() for t in a.tools}
    assert not names & {"approve", "approve_item", "post", "publish", "render"}


def test_tool_errors_go_back_to_the_agent(office):
    o, claude = office(use("show_item", {"id": 99}), say("I can't find #99."))
    o.say("raka", "show 99")
    result = o.threads["raka"].history[2]["content"][0]
    assert result["is_error"] is True and "99" in result["content"]


def test_maya_delegates_to_a_teammate(office):
    o, claude = office(
        use("ask_teammate", {"teammate": "sari", "message": "Draft a cat sketch please"}),
        say("On it! Nothing drafted yet, just confirming."),  # Sari's reply
        say("Sari is on it."),  # Maya's wrap-up
    )
    assert o.say("maya", "Get Sari going on a cat video") == "Sari is on it."
    sari = o.threads["sari"]
    assert [e["from"] for e in sari.feed] == ["maya", "agent"]
    assert sari.history[0]["content"] == "Message from Maya (Head of Content):\nDraft a cat sketch please"
    assert o.threads["maya"].history[2]["content"][0]["content"] == "On it! Nothing drafted yet, just confirming."


def test_checkin_tells_you_about_new_things_once(office):
    o, claude = office(say("Sure, here they are."))
    o.checkin()
    assert o.threads["raka"].feed[-1]["text"] == "My queue is empty. Want me to draft a few ideas?"
    q = PostQueue(o.team["raka"].desk.queue_path)
    q.add(IDEA)
    q.add({**IDEA, "hook": "Second"})
    q.save()
    o.checkin()
    assert o.threads["raka"].feed[-1]["text"] == "2 drafts waiting for your review: [[x:1]] [[x:2]]"
    count = len(o.threads["raka"].feed)
    o.checkin()  # nothing new: no repeat
    assert len(o.threads["raka"].feed) == count
    o.say("raka", "show me")  # the updates reach the agent with your next message
    first = claude.requests[0][-1]["content"]
    assert first.startswith("[Office updates]") and "2 drafts waiting" in first and first.endswith("show me")


def test_refusal_is_handled(office):
    o, _ = office(SimpleNamespace(stop_reason="refusal", content=[]))
    assert o.say("raka", "something odd") == "Sorry, I can't help with that one."
    assert o.threads["raka"].history[-1]["role"] == "assistant"


def test_a_missing_api_key_is_explained_not_crashed(office):
    o, claude = office()

    def no_key(**params):
        raise TypeError('"Could not resolve authentication method. Expected one of api_key, auth_token..."')

    claude.beta.messages.create = no_key
    assert o.say("raka", "hello") == ""
    assert o.threads["raka"].feed[-1] == {**o.threads["raka"].feed[-1], "from": "system",
                                          "text": "Raka can't reach Claude yet: set ANTHROPIC_API_KEY and restart the office."}
    assert o.status["raka"] == ""


def test_history_is_trimmed_from_the_front_at_an_exchange(monkeypatch):
    monkeypatch.setattr(chat, "MAX_HISTORY", 4)
    t = chat.Thread("/nonexistent/thread.json")
    t.history = [
        {"role": "user", "content": "a"}, {"role": "assistant", "content": []},
        {"role": "user", "content": [{"type": "tool_result"}]}, {"role": "assistant", "content": []},
        {"role": "user", "content": "b"}, {"role": "assistant", "content": []},
    ]  # fmt: skip
    t.trim()
    assert t.history[0] == {"role": "user", "content": "b"}


def wait_for_jobs(app):
    for _ in range(200):
        if not app.jobs:
            return
        time.sleep(0.02)
    raise AssertionError("job didn't finish")


def test_buttons_approve_then_post_to_x(office):
    session = FakeSession()
    o, _ = office(x_session=session)
    q = PostQueue(o.team["raka"].desk.queue_path)
    q.add(IDEA)
    q.save()
    app = server.OfficeApp(o)
    assert app.item("x", 1)["actions"] == ["approve", "reject"]
    with pytest.raises(ValueError):
        app.action("x", 1, "post")  # not approved yet
    app.action("x", 1, "approve")
    assert app.item("x", 1)["actions"] == ["post", "reject"]
    app.action("x", 1, "post")
    wait_for_jobs(app)
    assert session.payloads == [{"text": "Haze is back."}]
    assert app.item("x", 1)["status"] == "posted" and app.item("x", 1)["actions"] == []
    assert any(e["text"].startswith("Posted! [[x:1]]") for e in o.threads["raka"].feed)


def test_buttons_render_and_send_a_tiktok(office):
    o, _ = office()
    q = TIKTOK.queue(o.team["sari"].desk.queue_path)
    q.add(PLAN)
    q.save()
    app = server.OfficeApp(o)
    app.action("tiktok", 1, "approve")
    assert app.item("tiktok", 1)["actions"] == ["render", "publish", "reject"]
    app.action("tiktok", 1, "publish")
    wait_for_jobs(app)
    assert app.item("tiktok", 1)["status"] == "sent"
    assert any("[[tiktok:1]] is in your TikTok inbox" in e["text"] for e in o.threads["sari"].feed)


def test_sync_reports_through_maya(office):
    o, _ = office()
    app = server.OfficeApp(o, git=lambda: "Synced with GitHub: nothing of yours to push.")
    app.sync()
    for _ in range(200):
        if not app.syncing:
            break
        time.sleep(0.02)
    assert o.threads["maya"].feed[-1]["text"] == "Synced with GitHub: nothing of yours to push."


def test_http_only_accepts_local_office_requests(office):
    o, _ = office()
    httpd = server.serve(server.OfficeApp(o), port=0, checkin_minutes=60)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    try:
        page = urllib.request.urlopen(base + "/").read().decode()
        assert "<title>AI Office</title>" in page
        state = json.load(urllib.request.urlopen(base + "/api/state"))
        assert [a["name"] for a in state["agents"]] == ["Raka", "Sari", "Bima", "Maya"]

        def post(path, headers):
            req = urllib.request.Request(base + path, data=b"{}", method="POST", headers=headers)
            return urllib.request.urlopen(req).status

        with pytest.raises(urllib.error.HTTPError) as e:
            post("/api/checkin", {})  # no X-Office header: a cross-site form post
        assert e.value.code == 403
        with pytest.raises(urllib.error.HTTPError) as e:
            post("/api/checkin", {"X-Office": "1", "Host": "evil.example"})  # DNS rebinding
        assert e.value.code == 403
        assert post("/api/checkin", {"X-Office": "1"}) == 200
    finally:
        httpd.shutdown()
