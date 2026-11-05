import json
import time
from types import SimpleNamespace

import requests

from instagram_agent.__main__ import PLATFORM as INSTAGRAM
from office import server
from office.chat import Office
from office.desks import VideoDesk, XDesk
from office.team import build_team
from office.trading import TradingDesk
from tiktok_agent.__main__ import PLATFORM as TIKTOK


class Resp:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status

    def json(self):
        return self.data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(self.status_code)


class FakeBot:
    """Freqtrade's REST API, as far as the office reads it."""

    def __init__(self, up=True, closed=3):
        self.up, self.closed, self.auths = up, closed, []

    def get(self, url, params=None, auth=None, timeout=None):
        self.auths.append(auth)
        if not self.up:
            raise requests.ConnectionError("refused")
        path = url.rsplit("/api/v1/", 1)[1]
        return Resp({
            "ping": {"status": "pong"},
            "show_config": {"dry_run": True, "strategy": "NostalgiaForInfinityX8", "state": "running"},
            "profit": {"closed_trade_count": self.closed, "winning_trades": self.closed, "losing_trades": 0, "profit_closed_coin": 12.5},
            "balance": {"total": 1012.5, "starting_capital": 1000, "starting_capital_pct": 1.25, "stake": "USDT"},
            "status": [{"pair": "SOL/USDT", "profit_pct": -4.2, "open_date": "2026-11-04 10:00:00", "stake_amount": 160}],
            "trades": {"trades": [
                {"pair": "BTC/USDT", "is_open": False, "profit_pct": 2.1, "profit_abs": 4.2, "open_date": "a", "close_date": "2026-11-03", "exit_reason": "exit_signal"},
                {"pair": "ETH/USDT", "is_open": False, "profit_pct": 3.0, "profit_abs": 6.0, "open_date": "b", "close_date": "2026-11-04", "exit_reason": "roi"},
                {"pair": "SOL/USDT", "is_open": True}]},
        }[path])  # fmt: skip


def trading_folder(tmp_path):
    folder = tmp_path / "trading"
    (folder / "user_data").mkdir(parents=True)
    (folder / "user_data" / "config.json").write_text(json.dumps({"api_server": {"username": "freqtrader"}}))
    (folder / ".env").write_text("FREQTRADE__API_SERVER__PASSWORD=pw\n")
    return folder


def test_the_desk_reads_the_bot_in_plain_numbers(tmp_path):
    bot = FakeBot()
    desk = TradingDesk(trading_folder(tmp_path), bot)
    status = desk.summary()
    assert status["running"] and status["paper"] and status["strategy"] == "NostalgiaForInfinityX8"
    assert (status["wallet"], status["change_pct"], status["closed"], status["closed_profit"]) == (1012.5, 1.25, 3, 12.5)
    assert status["open"] == [{"pair": "SOL/USDT", "profit_pct": -4.2, "since": "2026-11-04 10:00:00", "stake": 160}]
    assert ("freqtrader", "pw") in bot.auths
    assert [t["pair"] for t in desk.recent_trades()] == ["ETH/USDT", "BTC/USDT"]  # newest closed first, open ones left out


def test_a_bot_that_isnt_running_is_said_plainly(tmp_path):
    assert TradingDesk(trading_folder(tmp_path), FakeBot(up=False)).summary() == {"set_up": True, "running": False}


def test_start_and_stop_use_the_trading_helper(tmp_path):
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(returncode=0 if cmd[-1] == "start" else 1, stdout="Docker isn't running\n", stderr="")

    desk = TradingDesk(trading_folder(tmp_path), FakeBot(), run=run)
    desk.control("start")
    assert calls[0][-1] == "start" and calls[0][-2].endswith(("trading.ps1", "trading.sh"))
    try:
        desk.control("stop")
        raise AssertionError("should fail")
    except RuntimeError as e:
        assert "Docker isn't running" in str(e)


def test_dewi_reports_closed_trades_and_the_buttons_work(tmp_path):
    bot = FakeBot(closed=3)
    started = []
    trading = TradingDesk(trading_folder(tmp_path), bot, run=lambda cmd, **kw: started.append(cmd[-1]) or SimpleNamespace(returncode=0, stdout="", stderr=""))
    team = build_team(XDesk(tmp_path / "x.json"), VideoDesk(TIKTOK, tmp_path / "t.json"), VideoDesk(INSTAGRAM, tmp_path / "i.json"), trading)
    assert {t["name"] for t in team["dewi"].tools} == {"trading_status", "recent_trades"}
    assert "never promise profits" in team["dewi"].system.lower()
    office = Office(team, tmp_path / "data", engine=SimpleNamespace(name="test"))
    office.checkin()  # first look: remembers 3 closed trades, says nothing
    assert office.threads["dewi"].feed == []
    bot.closed = 5
    office.checkin()
    said = office.threads["dewi"].feed[-1]["text"]
    assert "closed 2 trades (pretend money)" in said and "+1.25%" in said
    assert "Dewi (trading bot)" in office._head_tool("team_overview", {})

    app = server.OfficeApp(office)
    assert app.trading_status()["enabled"] and app.trading_status()["wallet"] == 1012.5
    app.trading_control("start")
    for _ in range(100):
        if "trading" not in app.jobs:
            break
        time.sleep(0.02)
    assert started == ["start"] and "The trading bot is running" in office.threads["dewi"].feed[-1]["text"]
