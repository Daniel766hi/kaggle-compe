"""Draw a Kaggle cover image (560x280) from a real time series in a dataset file.

    pip install matplotlib
    python scripts/make_cover.py build/defi/defi_tvl_history.csv date tvl_usd \\
        --title "DeFi Daily" --subtitle "TVL · Stablecoins · DEX · Yields" --out assets/defi-cover.png

Kaggle crops the cover at 560x280 px (header) and the centre 280x280 px (thumbnail),
so the image is drawn at exactly that size with the title centred.
"""

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

SURFACE = "#1a1a19"
SERIES = "#3987e5"
TEXT = "#f0efec"
TEXT_SECONDARY = "#c3c2b7"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("csv")
    p.add_argument("date_col")
    p.add_argument("value_col")
    p.add_argument("--title", required=True)
    p.add_argument("--subtitle", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--where", help="filter as column=value, e.g. city=Jakarta")
    p.add_argument("--since", help="first date to plot, e.g. 2019-06-01")
    p.add_argument("--rolling", type=int, default=1, help="rolling mean window to smooth the line")
    args = p.parse_args()

    df = pd.read_csv(args.csv, parse_dates=[args.date_col])
    if args.where:
        col, val = args.where.split("=", 1)
        df = df[df[col].astype(str) == val]
    if args.since:
        df = df[df[args.date_col] >= args.since]
    series = df.set_index(args.date_col)[args.value_col].sort_index().rolling(args.rolling, min_periods=1).mean()

    fig = plt.figure(figsize=(5.6, 2.8), dpi=100, facecolor=SURFACE)
    ax = fig.add_axes([0, 0, 1, 0.62])
    ax.set_facecolor(SURFACE)
    ax.fill_between(series.index, series.values, series.min() * 0.9, color=SERIES, alpha=0.35, linewidth=0)
    ax.plot(series.index, series.values, color=SERIES, linewidth=2)
    ax.set_xlim(series.index.min(), series.index.max())
    ax.set_ylim(series.min() * 0.9, series.max() * 1.05)
    ax.axis("off")

    fig.text(0.5, 0.80, args.title, ha="center", va="center", color=TEXT, fontsize=24, fontweight="bold")
    fig.text(0.5, 0.67, args.subtitle, ha="center", va="center", color=TEXT_SECONDARY, fontsize=10)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=100, facecolor=SURFACE)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
