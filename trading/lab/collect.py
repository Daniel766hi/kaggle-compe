"""Add the latest backtest's numbers to results.json (run inside the Freqtrade image).

python collect.py STRATEGY PERIOD
"""

import json
import sys
from pathlib import Path

from freqtrade.data.btanalysis import get_latest_backtest_filename, load_backtest_stats

strategy, period = sys.argv[1], sys.argv[2]
folder = Path("/freqtrade/user_data/backtest_results")
stats = load_backtest_stats(folder, get_latest_backtest_filename(folder))["strategy"][strategy]
keys = ("total_trades", "profit_total", "cagr", "max_relative_drawdown", "calmar", "sharpe", "sortino", "winrate",
        "profit_factor", "market_change", "backtest_start", "backtest_end", "holding_avg")  # fmt: skip
row = {"strategy": strategy, "period": period, **{k: stats.get(k) for k in keys}}
results = Path("/lab/results.json")
rows = json.loads(results.read_text()) if results.exists() else []
results.write_text(json.dumps([*rows, row], indent=1, default=str))
print(json.dumps(row, default=str))
