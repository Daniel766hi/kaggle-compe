"""Draw the Kaggle cover image from the real DeFi TVL history.

    pip install matplotlib
    python -m defi_dataset --dry-run          # writes build/defi_tvl_history.csv
    python scripts/make_cover.py build/defi_tvl_history.csv

Kaggle crops the cover at 560x280 px (header) and the centre 280x280 px (thumbnail),
so the image is drawn at exactly that size with the title centred.
"""

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

SURFACE = "#1a1a19"
SERIES = "#3987e5"
TEXT = "#f0efec"
TEXT_SECONDARY = "#c3c2b7"
OUT = Path(__file__).resolve().parent.parent / "assets" / "dataset-cover-image.png"


def main(csv_path):
    df = pd.read_csv(csv_path, parse_dates=["date"])
    df = df[df["date"] >= "2019-06-01"]

    fig = plt.figure(figsize=(5.6, 2.8), dpi=100, facecolor=SURFACE)
    ax = fig.add_axes([0, 0, 1, 0.62])
    ax.set_facecolor(SURFACE)
    ax.fill_between(df["date"], df["tvl_usd"], color=SERIES, alpha=0.35, linewidth=0)
    ax.plot(df["date"], df["tvl_usd"], color=SERIES, linewidth=2)
    ax.set_xlim(df["date"].min(), df["date"].max())
    ax.set_ylim(0, df["tvl_usd"].max() * 1.05)
    ax.axis("off")

    fig.text(0.5, 0.80, "DeFi Daily", ha="center", va="center", color=TEXT, fontsize=24, fontweight="bold")
    fig.text(0.5, 0.67, "TVL · Stablecoins · DEX · Yields", ha="center", va="center",
             color=TEXT_SECONDARY, fontsize=10)

    OUT.parent.mkdir(exist_ok=True)
    fig.savefig(OUT, dpi=100, facecolor=SURFACE)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "build/defi_tvl_history.csv")
