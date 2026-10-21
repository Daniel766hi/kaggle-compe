"""Draw the writeup cover image from the feature tables (real data only).

    python bdb2027_writeup/make_cover.py FEATURE_DIR DATA_DIR OUT.png
"""

import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from nfl_bdb2027.movement import fit_as_profile, robust_envelope

feat, data, out = sys.argv[1:4]
gb = pd.read_parquet(f"{feat}/game_bins.parquet")
env = robust_envelope(gb, ["nfl_id"], k=2)
prof = pd.DataFrame({p: fit_as_profile(e.bin, e.acc_max) for p, e in env.groupby("nfl_id")}).T.astype(float).dropna()
pos = pd.read_csv(f"{data}/combine_results.csv").set_index("nfl_id").combine_position
prof = prof.join(pos).dropna()

BG, INK = "#0f1720", "#f4f3ee"
COLORS = {"WR": "#2a78d6", "DB": "#eb6834", "TE": "#1baf7a", "DL": "#eda100", "OL": "#e87ba4"}
fig = plt.figure(figsize=(12.8, 6.4), dpi=100, facecolor=BG)
ax = fig.add_axes([0.05, 0.1, 0.55, 0.8], facecolor=BG)
v = np.linspace(0, 12, 60)
for p, r in prof.sample(frac=1, random_state=0).iterrows():
    ax.plot(v, np.clip(r.A0 * (1 - v / r.S0), 0, None), color=COLORS[r.combine_position], alpha=0.28, lw=1.1)
for k, c in COLORS.items():
    ax.plot([], [], color=c, lw=3, label=k)
ax.legend(loc="upper right", frameon=False, labelcolor=INK, fontsize=13, ncol=5, handlelength=1.2)
ax.set(xlim=(0, 12), ylim=(0, 14))
ax.set_xlabel("speed (yd/s)", color=INK, fontsize=12)
ax.set_ylabel("acceleration (yd/s²)", color=INK, fontsize=12)
ax.tick_params(colors=INK)
for sp in ax.spines.values():
    sp.set_visible(False)
ax.text(0.2, 0.6, f"{len(prof)} rookies' in-game\nacceleration-speed engines", color=INK, fontsize=11, alpha=0.8)
fig.text(0.64, 0.74, "How many\nNFL games is\nthe Combine worth?", color=INK, fontsize=30, fontweight="bold", va="top")
fig.text(0.64, 0.30, "Top speed  ≈ 5 games\nAcceleration  < 1 game", color="#eda100", fontsize=20, va="top",
         fontweight="bold")
fig.text(0.64, 0.12, "NFL Big Data Bowl 2027", color=INK, fontsize=12, alpha=0.7)
fig.savefig(out, facecolor=BG)
print("saved", out, len(prof), "profiles")
