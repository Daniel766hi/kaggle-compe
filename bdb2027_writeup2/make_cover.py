"""Draw the cover image for the second writeup from the lateral envelopes (real data only).

    python bdb2027_writeup2/make_cover.py FEATURE_DIR DATA_DIR OUT.png
"""

import sys

import matplotlib.pyplot as plt
import pandas as pd

from nfl_bdb2027.movement import BIN, robust_envelope

feat, data, out = sys.argv[1:4]
env = robust_envelope(pd.read_parquet(f"{feat}/game_lat.parquet"), ["nfl_id"], col="lat_max", k=2)
pos = pd.read_csv(f"{data}/combine_results.csv").set_index("nfl_id").combine_position
env = env.join(pos, on="nfl_id")
env = env[(env.bin + 0.5) * BIN >= 1]

BG, INK = "#0f1720", "#f4f3ee"
COLORS = {"WR": "#2a78d6", "DB": "#eb6834", "TE": "#1baf7a", "DL": "#eda100", "OL": "#e87ba4"}
fig = plt.figure(figsize=(12.8, 6.4), dpi=100, facecolor=BG)
ax = fig.add_axes([0.05, 0.1, 0.55, 0.8], facecolor=BG)
for pid, e in env.groupby("nfl_id"):
    p = e.combine_position.iloc[0]
    if p in COLORS:
        ax.plot((e.bin + 0.5) * BIN, e.lat_max, color=COLORS[p], alpha=0.18, lw=1)
for k, c in COLORS.items():
    ax.plot([], [], color=c, lw=3, label=k)
ax.legend(loc="upper right", frameon=False, labelcolor=INK, fontsize=13, ncol=5, handlelength=1.2)
ax.set(xlim=(1, 11), ylim=(0, 13))
ax.set_xlabel("speed (yd/s)", color=INK, fontsize=12)
ax.set_ylabel("sideways acceleration (yd/s²)", color=INK, fontsize=12)
ax.tick_params(colors=INK)
for sp in ax.spines.values():
    sp.set_visible(False)
ax.text(1.2, 0.6, f"{env.nfl_id.nunique()} rookies' in-game turning envelopes", color=INK, fontsize=11, alpha=0.8)
fig.text(0.64, 0.74, "Bend,\nDon't Brake", color=INK, fontsize=34, fontweight="bold", va="top")
fig.text(0.64, 0.42, "The turning engine\nthe Combine cannot see", color="#eda100", fontsize=19, va="top",
         fontweight="bold")
fig.text(0.64, 0.12, "NFL Big Data Bowl 2027", color=INK, fontsize=12, alpha=0.7)
fig.savefig(out, facecolor=BG)
print("saved", out)
