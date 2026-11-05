"""The trading desk: what the paper-trading bot (trading/, Freqtrade) is doing, for the office.

It reads the bot's own API on this computer (http://127.0.0.1:8080, the password from
trading/.env) and starts or stops the bot with trading/trading.ps1 (Windows) or trading.sh.
Reading is all an agent can do; start and stop are buttons. The bot trades with pretend money
(dry run) unless its config says otherwise, and the summary always says which.
"""

import json
import os
import subprocess
from pathlib import Path

import requests

API = "http://127.0.0.1:8080/api/v1"


class TradingDesk:
    key, title = "trading", "Trading (paper)"

    def __init__(self, folder=None, session=None, run=subprocess.run):
        self.folder = Path(folder or Path(__file__).resolve().parents[1] / "trading")
        self.session = session or requests.Session()
        self.run = run

    def set_up(self):
        return (self.folder / ".env").exists()

    def _login(self):
        password = ""
        env = self.folder / ".env"
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("FREQTRADE__API_SERVER__PASSWORD="):
                    password = line.split("=", 1)[1].strip()
        config = json.loads((self.folder / "user_data" / "config.json").read_text(encoding="utf-8"))
        return config.get("api_server", {}).get("username", "freqtrader"), password

    def _get(self, path, **params):
        resp = self.session.get(f"{API}/{path}", params=params, auth=self._login(), timeout=5)
        resp.raise_for_status()
        return resp.json()

    def summary(self):
        """Running? The wallet, the open trades and the closed ones, in plain numbers."""
        out = {"set_up": self.set_up(), "running": False}
        try:
            self.session.get(f"{API}/ping", timeout=3).raise_for_status()
        except requests.RequestException:
            return out
        try:
            config, profit, balance = self._get("show_config"), self._get("profit"), self._get("balance")
            open_trades = self._get("status")
        except (requests.RequestException, ValueError) as e:
            return {**out, "running": True, "error": f"The bot answers but its numbers couldn't be read: {e}"}
        start = balance.get("starting_capital") or 0
        out.update(
            running=True,
            paper=bool(config.get("dry_run", True)),
            strategy=config.get("strategy", ""),
            state=config.get("state", ""),
            wallet=round(float(balance.get("total") or 0), 2),
            start=round(float(start), 2),
            change_pct=round(float(balance.get("starting_capital_pct") or 0), 2),
            closed=int(profit.get("closed_trade_count") or 0),
            wins=int(profit.get("winning_trades") or 0),
            losses=int(profit.get("losing_trades") or 0),
            closed_profit=round(float(profit.get("profit_closed_coin") or 0), 2),
            open=[{"pair": t.get("pair"), "profit_pct": round(float(t.get("profit_pct") or 0), 2),
                   "since": t.get("open_date"), "stake": round(float(t.get("stake_amount") or 0), 2)}
                  for t in open_trades],  # fmt: skip
            currency=balance.get("stake", "USDT"),
        )
        return out

    def recent_trades(self, n=10):
        """The last closed trades, newest first."""
        data = self._get("trades", limit=200, order_by_id=False)
        closed = [t for t in data.get("trades", []) if not t.get("is_open")]
        closed.sort(key=lambda t: t.get("close_date") or "", reverse=True)
        return [{"pair": t.get("pair"), "profit_pct": t.get("profit_pct"), "profit": t.get("profit_abs"),
                 "opened": t.get("open_date"), "closed": t.get("close_date"), "why": t.get("exit_reason")}
                for t in closed[:n]]  # fmt: skip

    def control(self, action):
        """Start or stop the bot with its own helper script (Docker Desktop must be running)."""
        if action not in ("start", "stop"):
            raise ValueError(f"unknown action {action}")
        if os.name == "nt":
            cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(self.folder / "trading.ps1"), action]
        else:
            cmd = ["bash", str(self.folder / "trading.sh"), action]
        result = self.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3 * 3600)
        tail = "\n".join((result.stdout or "").strip().splitlines()[-4:] + (result.stderr or "").strip().splitlines()[-2:])
        if result.returncode:
            raise RuntimeError(tail or f"the trading helper stopped with code {result.returncode}")
        return tail
