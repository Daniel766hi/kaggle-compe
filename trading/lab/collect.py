"""Add the latest backtest's numbers to results.json (run inside the Freqtrade image).

python collect.py STRATEGY PERIOD

Besides Freqtrade's own statistics it measures the honest worst fall: the wallet's value every
hour with open trades counted at the market price. Freqtrade's drawdown only counts closed
trades, so a strategy that holds losing trades instead of selling them can look like it never
fell at all. Each trade is valued with its full final stake from the moment it opened (cautious
for strategies that buy more later).
"""

import json
import sys
from pathlib import Path

import pandas as pd

from freqtrade.data.btanalysis import get_latest_backtest_filename, load_backtest_data, load_backtest_stats
from freqtrade.data.history import load_pair_history

strategy, period = sys.argv[1], sys.argv[2]
folder = Path("/freqtrade/user_data/backtest_results")
latest = get_latest_backtest_filename(folder)
stats = load_backtest_stats(folder, latest)["strategy"][strategy]
trades = load_backtest_data(folder, strategy, latest)
exchange = json.loads(Path("/lab/config.json").read_text())["exchange"]["name"]
datadir = Path("/freqtrade/user_data/data") / exchange
wallet = float(stats.get("starting_balance") or 1000)


def honest_drawdown():
    if trades.empty:
        return 0.0
    hours = pd.date_range(pd.Timestamp(stats["backtest_start"], tz="UTC"), pd.Timestamp(stats["backtest_end"], tz="UTC"), freq="1h")
    equity = pd.Series(wallet, index=hours)
    prices = {}
    for t in trades.itertuples():
        equity[equity.index >= t.close_date] += t.profit_abs  # what the trade made or lost, once closed
        if t.pair not in prices:
            candles = load_pair_history(t.pair, "1h", datadir, data_format="feather")
            prices[t.pair] = candles.set_index("date")["close"] if not candles.empty else pd.Series(dtype=float)
        close = prices[t.pair]
        open_window = close[(close.index >= t.open_date) & (close.index < t.close_date)]
        stake = getattr(t, "max_stake_amount", None) or t.stake_amount
        unrealized = (stake * (open_window / t.open_rate - 1)).reindex(hours).fillna(0.0)
        equity += unrealized  # while open: what it would fetch at the market price
    peak = equity.cummax()
    return float(((peak - equity) / peak).max())


keys = ("total_trades", "profit_total", "cagr", "max_relative_drawdown", "calmar", "sharpe", "sortino", "winrate",
        "profit_factor", "market_change", "backtest_start", "backtest_end", "holding_avg")  # fmt: skip
row = {"strategy": strategy, "period": period, **{k: stats.get(k) for k in keys}}
try:
    row["honest_drawdown"] = honest_drawdown()
except Exception as e:  # keep Freqtrade's own numbers even if this extra check can't run
    print(f"honest drawdown not measured: {e!r}", file=sys.stderr)
if not trades.empty:
    row["worst_trade"] = float(trades["profit_ratio"].min())
    row["longest_hold_days"] = round(float(trades["trade_duration"].max()) / 1440, 1)
    row["open_at_end"] = int((trades["exit_reason"] == "force_exit").sum())
results = Path("/lab/results.json")
rows = json.loads(results.read_text()) if results.exists() else []
results.write_text(json.dumps([*rows, row], indent=1, default=str))
print(json.dumps(row, default=str))
