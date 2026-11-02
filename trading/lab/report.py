"""The lab's verdict: python report.py results.json > report.md

A strategy only counts as good if it made money in BOTH years (the first year checks it, the
second is unseen data), beat simply holding the coins in at least one, and kept its worst fall
(drawdown) bearable. Ranked by the weaker of its two years, so luck in one year doesn't win.
"""

import json
import sys

rows = json.load(open(sys.argv[1]))
by = {}
for r in rows:
    by.setdefault(r["strategy"], {})[r["period"]] = r


def pct(x):
    return "n/a" if x is None else f"{x * 100:+.1f}%"


def fmt(r):
    if not r:
        return "failed", "", "", ""
    return pct(r["profit_total"]), f"{(r['max_relative_drawdown'] or 0) * 100:.1f}%", str(r["total_trades"]), pct(r["market_change"])


scored = []
for name, periods in by.items():
    a, b = periods.get("A"), periods.get("B")
    profits = [p["profit_total"] for p in (a, b) if p and p.get("profit_total") is not None]
    worst = min(profits) if len(profits) == 2 else -9
    drawdown = max(((p or {}).get("max_relative_drawdown") or 0) for p in (a, b))
    beats = any(p and (p["profit_total"] or 0) > (p["market_change"] or 0) for p in (a, b))
    good = worst > 0 and drawdown < 0.35 and beats
    scored.append((good, worst, name, a, b, drawdown))
scored.sort(key=lambda s: (s[0], s[1]), reverse=True)

print("| Rank | Strategy | Year 1 profit | Year 1 worst fall | Year 1 trades | Year 1 hold | Year 2 profit (unseen) | "
      "Year 2 worst fall | Year 2 trades | Year 2 hold | Passes |")  # fmt: skip
print("|---|---|---|---|---|---|---|---|---|---|---|")
for n, (good, worst, name, a, b, drawdown) in enumerate(scored, 1):
    print(f"| {n} | {name} | " + " | ".join(fmt(a)) + " | " + " | ".join(fmt(b)) + f" | {'✅' if good else '❌'} |")
print()
winners = [s[2] for s in scored if s[0]]
print("**Passes**: made money in both years, beat holding in at least one, worst fall under 35%.")
print(f"\n**Best**: {winners[0] if winners else 'none passed: keep paper trading and holding instead'}")
