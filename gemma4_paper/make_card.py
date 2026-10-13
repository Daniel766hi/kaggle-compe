"""Render the Kaggle Writeup card / thumbnail image (results/card.png, 1280x640).

Numbers are Hit@10 from results/localization_summary_v1.json (116 labelled tasks).
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch

HERE = Path(__file__).resolve().parent
for f in ("Inter-Regular.otf", "Inter-Medium.otf", "Inter-SemiBold.otf", "Inter-Bold.otf"):
    p = Path("/usr/share/fonts/opentype/inter") / f
    if p.exists():
        font_manager.fontManager.addfont(str(p))
plt.rcParams["font.family"] = ["Inter", "DejaVu Sans"]

SURFACE, INK, INK2, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8984"
ACCENT, DEEMPH = "#2a78d6", "#c9c8c2"

s = json.loads((HERE / "results" / "localization_summary_v1.json").read_text())
rows = [
    ("search_similar_code, keywords\n(as the harness prompt suggests)", s["tool_kw"]["hit10"], DEEMPH),
    ("search_similar_code, full issue text", s["tool_issue"]["hit10"], DEEMPH),
    ("BM25 over function source\n(no model, same issue text)", s["bm25"]["hit10"], ACCENT),
]

fig = plt.figure(figsize=(12.8, 6.4), dpi=100, facecolor=SURFACE)
fig.text(0.05, 0.86, "The Query Gap", fontsize=40, fontweight="bold", color=INK)
fig.text(0.05, 0.775, "Why the Gemma 4 harness's semantic code search rarely finds the bug",
         fontsize=19, color=INK2)

ax = fig.add_axes([0.05, 0.17, 0.90, 0.50], facecolor=SURFACE)
ax.set_xlim(0, 100)
ax.set_ylim(-0.6, len(rows) - 0.4)
ax.axis("off")
h = 0.42
for i, (label, v, color) in enumerate(reversed(rows)):
    y = i
    pct = 100 * v
    ax.add_patch(FancyBboxPatch((38, y - h / 2), pct * 0.80, h, boxstyle="round,pad=0,rounding_size=0.06",
                                mutation_aspect=1 / 25, facecolor=color, edgecolor="none"))
    ax.text(36.5, y, label, ha="right", va="center", fontsize=15, color=INK, linespacing=1.15)
    ax.text(38 + pct * 0.80 + 1.2, y, f"{pct:.1f}%", ha="left", va="center", fontsize=20,
            fontweight="bold", color=INK)
fig.text(0.05, 0.075, "Share of 116 development tasks where a function the reference fix edits is in the top 10",
         fontsize=14, color=MUTED)
fig.text(0.95, 0.885, "Gemma 4 Developer Agent\nPaper Track", fontsize=14, color=MUTED, ha="right", va="center",
         linespacing=1.3)
out = HERE / "results" / "card.png"
fig.savefig(out, facecolor=SURFACE)
print(out)
