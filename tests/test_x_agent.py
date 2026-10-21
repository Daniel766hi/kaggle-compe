import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from x_agent import __main__ as cli
from x_agent import brain, text
from x_agent.queue import PostQueue
from x_agent.x_client import XClient

IDEA = {"pillar": "Indonesia in data", "hook": "Haze season starts", "posts": ["Haze is back."], "sources": [], "fact_check": ""}


class FakeClaude:
    """Stands in for anthropic.Anthropic(); returns queued responses and records requests."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    @contextmanager
    def _stream(self, **params):
        self.requests.append(params)
        message = self.responses.pop(0)
        yield SimpleNamespace(get_final_message=lambda: message)


def message(content, stop_reason="end_turn"):
    return SimpleNamespace(stop_reason=stop_reason, stop_details=None, content=content)


def text_block(data):
    return SimpleNamespace(type="text", text=json.dumps(data))


class FakeResponse:
    def __init__(self, status, data):
        self.status_code, self._data, self.text = status, data, json.dumps(data)

    def json(self):
        return self._data


class FakeSession:
    def __init__(self, fail_at=None):
        self.payloads, self.fail_at = [], fail_at

    def post(self, url, json, timeout):
        self.payloads.append(json)
        if len(self.payloads) == self.fail_at:
            return FakeResponse(429, {"title": "Too Many Requests"})
        return FakeResponse(201, {"data": {"id": str(100 + len(self.payloads))}})


def test_weighted_length_counts_links_and_emoji_like_x():
    assert text.weighted_length("abc") == 3
    assert text.weighted_length("see https://www.kaggle.com/datasets/some/very-long-slug") == 4 + 23
    assert text.weighted_length("🔥 ok") == 2 + 3
    assert text.problems(["x" * 281]) == ["post 1 is 281 characters (limit 280)"]
    assert text.problems(["ok", " "]) == ["post 2 is empty"]


def test_queue_round_trip_and_order(tmp_path):
    q = PostQueue(tmp_path / "q.json")
    a, b = q.add(IDEA), q.add({**IDEA, "hook": "Rupiah"})
    q.set_status(b["id"], "approved")["approved_at"] = "2026-10-20T01:00:00+00:00"
    q.set_status(a["id"], "approved")["approved_at"] = "2026-10-20T02:00:00+00:00"
    q.save()
    q2 = PostQueue(tmp_path / "q.json")
    assert [i["id"] for i in q2.items] == [1, 2]
    assert q2.next_approved()["id"] == 2  # approved first, posted first
    assert q2.recent_hooks() == ["Haze season starts", "Rupiah"]


def test_post_thread_chains_replies():
    session = FakeSession()
    assert XClient(session).post_thread(["one", "two", "three"]) == ["101", "102", "103"]
    assert session.payloads[0] == {"text": "one"}
    assert session.payloads[2] == {"text": "three", "reply": {"in_reply_to_tweet_id": "102"}}


def test_failed_thread_keeps_what_was_posted(tmp_path):
    q = PostQueue(tmp_path / "q.json")
    q.add({**IDEA, "posts": ["one", "two"]}, status="approved")
    code = cli.cmd_post(q, SimpleNamespace(dry_run=False), XClient(FakeSession(fail_at=2)))
    item = q.get(1)
    assert code == 1 and item["status"] == "failed"
    assert item["tweet_ids"] == ["101"] and "429" in item["error"]


def test_post_publishes_oldest_approved_only(tmp_path):
    q = PostQueue(tmp_path / "q.json")
    q.add(IDEA)  # still a draft
    q.add(IDEA, status="approved")
    session = FakeSession()
    assert cli.cmd_post(q, SimpleNamespace(dry_run=False), XClient(session)) == 0
    assert len(session.payloads) == 1
    assert q.get(2)["status"] == "posted" and q.get(2)["url"].endswith("/101")
    assert q.get(1)["status"] == "draft"


def test_too_long_post_is_never_sent(tmp_path):
    q = PostQueue(tmp_path / "q.json")
    q.add({**IDEA, "posts": ["x" * 300]}, status="approved")
    session = FakeSession()
    assert cli.cmd_post(q, SimpleNamespace(dry_run=False), XClient(session)) == 1
    assert session.payloads == [] and q.get(1)["status"] == "failed"


def test_generate_ideas_resumes_paused_search_and_reads_json():
    search = SimpleNamespace(type="server_tool_use")
    claude = FakeClaude(
        message([search], stop_reason="pause_turn"),
        message([search, SimpleNamespace(type="web_search_tool_result"), text_block({"ideas": [IDEA]})]),
    )
    ideas = brain.generate_ideas("profile", 1, avoid=["Old idea"], client=claude)
    assert ideas == [IDEA]
    first, second = claude.requests
    assert first["tools"][0]["type"] == "web_search_20260209"
    assert "Old idea" in first["messages"][0]["content"]
    assert second["messages"][1] == {"role": "assistant", "content": [search]}
    assert first["output_config"]["format"]["schema"] == brain.IDEAS_SCHEMA


def test_refusal_is_an_error():
    claude = FakeClaude(message([], stop_reason="refusal"))
    with pytest.raises(brain.AgentError):
        brain.revise("profile", {**IDEA}, "shorter", client=claude)


def test_autopilot_tops_up_and_auto_approves_only_safe_drafts(tmp_path, monkeypatch):
    monkeypatch.setenv("X_AUTO_APPROVE", "true")
    monkeypatch.setattr(brain, "load_profile", lambda: "profile")
    risky = {**IDEA, "hook": "A statistic", "fact_check": "check the 2019 figure"}
    claude = FakeClaude(message([text_block({"ideas": [IDEA, risky]})]))
    q = PostQueue(tmp_path / "q.json")
    session = FakeSession()
    args = SimpleNamespace(min_drafts=3, count=2, dry_run=False)
    assert cli.cmd_autopilot(q, args, XClient(session), claude) == 0
    assert [i["status"] for i in q.items] == ["posted", "draft"]
    assert session.payloads == [{"text": "Haze is back."}]


def test_posted_items_cannot_be_approved_again(tmp_path):
    q = PostQueue(tmp_path / "q.json")
    q.add(IDEA, status="approved")
    cli.cmd_post(q, SimpleNamespace(dry_run=False), XClient(FakeSession()))
    with pytest.raises(SystemExit):
        cli.cmd_set_status(q, SimpleNamespace(ids=[1], status="approved"))
