# %% [markdown]
# # Commodity prices since 1960: cycles, Indonesia's exports and what moves together
#
# This notebook explores **[World Commodity Prices Monthly (1960-now)](https://www.kaggle.com/datasets/danielaijdkx/world-commodity-prices-monthly-pink-sheet)**:
# the World Bank's "Pink Sheet" of monthly prices for 71 commodities and 16 price indices.
#
# **Questions answered**
# 1. How have energy, food and metal prices moved over 65 years, and where are they now?
# 2. Where do Indonesia's key export commodities sit against their own 10-year range?
# 3. Which commodities swing the most from month to month?
# 4. Do Indonesia's commodities move with oil, or on their own?
# 5. After a price peak, how far do prices fall, and how long until they recover?
#
# All figures are in **nominal US dollars**, as published; the text below the charts is computed from the
# data each time the notebook runs.

# %%
import glob
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e6e5e0", "#fcfcfb"
C = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
    "axes.titlesize": 13, "axes.titleweight": "bold", "axes.titlecolor": INK, "axes.titlelocation": "left",
    "font.size": 10.5, "lines.linewidth": 2, "figure.figsize": (11, 4.6), "figure.dpi": 110,
    "legend.frameon": False, "axes.xmargin": 0.01,
})


def find(name):
    """Locate a dataset file on Kaggle (/kaggle/input) or locally (DATA_ROOT)."""
    for root in ("/kaggle/input", os.environ.get("DATA_ROOT", "../input")):
        hits = glob.glob(f"{root}/**/{name}", recursive=True)
        if hits:
            return hits[0]
    raise FileNotFoundError(name)


# %%
prices = pd.read_csv(find("prices_monthly.csv"), parse_dates=["month"])
indices = pd.read_csv(find("indices_monthly.csv"), parse_dates=["month"])
summary = pd.read_csv(find("commodities.csv"), parse_dates=["first_month", "last_month", "all_time_high_month"])
latest = prices["month"].max()
wide = prices.pivot(index="month", columns="commodity_id", values="price")
names = summary.set_index("commodity_id")["commodity"]
idn = summary.loc[summary["indonesia_major"], "commodity_id"].tolist()
print(f"{prices['commodity_id'].nunique()} commodities, {prices['month'].min():%B %Y} to {latest:%B %Y}; "
      f"{len(prices):,} monthly prices. Indonesia's key commodities: {', '.join(names[idn])}")

# %% [markdown]
# ## 1. Sixty-five years of commodity cycles
#
# The World Bank's indices (2010 = 100) on a log scale, so equal heights mean equal percentage moves.
# Energy has the widest swings; metals and food move in long waves.

# %%
fig, ax = plt.subplots()
for col, color, label in (("energy", C[1], "Energy"), ("food", C[2], "Food"), ("metals_minerals", C[0], "Metals & minerals"),
                          ("precious_metals", C[3], "Precious metals")):
    ax.plot(indices["month"], indices[col], color=color, label=label, lw=1.6)
ax.set_yscale("log")
ax.set_title("World Bank commodity price indices (nominal US$, 2010 = 100, log scale)")
ax.legend(loc="upper left")
for year, text in ((1974, "1st oil shock"), (1980, "2nd oil shock"), (2008, "2008 peak"), (2022, "2022 energy spike")):
    ax.axvline(pd.Timestamp(f"{year}-01-01"), color=GRID, lw=1, zorder=0)
    ax.text(pd.Timestamp(f"{year}-03-01"), ax.get_ylim()[1] * 0.75, text, fontsize=8.5, color=INK2)
plt.show()

now = indices.iloc[-1]
year_ago = indices[indices["month"] == latest - pd.DateOffset(years=1)].iloc[0]
for col, label in (("energy", "Energy"), ("food", "Food"), ("metals_minerals", "Metals"), ("precious_metals", "Precious metals")):
    peak = indices.loc[indices[col].idxmax()]
    print(f"{label:16s} {now[col]:6.1f} in {latest:%b %Y} ({(now[col] / year_ago[col] - 1) * 100:+.1f}% on a year ago); "
          f"record {peak[col]:.1f} in {peak['month']:%b %Y}")

# %% [markdown]
# ## 2. Indonesia's commodities against their own 10-year range
#
# Each bar shows the latest price as a percentile of the last 120 months: 100 means the highest price in ten
# years, 0 the lowest. This matters for export earnings, the rupiah and state revenue (royalties and export
# levies are tied to these prices).

# %%
s = summary[summary["indonesia_major"]].sort_values("percentile_10y")
fig, ax = plt.subplots(figsize=(11, 0.55 * len(s) + 1))
colors = [C[7] if p >= 80 else C[0] if p <= 20 else INK2 for p in s["percentile_10y"]]
ax.barh(s["commodity"], s["percentile_10y"], color=colors)
ax.axvline(50, color=INK2, lw=1, ls="--")
for y, (p, ch) in enumerate(zip(s["percentile_10y"], s["change_12m_pct"])):
    ax.text(p + 1, y, f"{p:.0f}   ({ch:+.0f}% in 12 months)" if pd.notna(ch) else f"{p:.0f}", va="center", fontsize=9, color=INK2)
ax.set_xlim(0, 125)
ax.set_xlabel("Latest price as a percentile of the last 10 years (red: top fifth, blue: bottom fifth)")
ax.set_title(f"Where Indonesia's key commodities stand, {latest:%B %Y}")
ax.grid(axis="y", visible=False)
plt.show()

high = s[s["percentile_10y"] >= 80]["commodity"].tolist()
low = s[s["percentile_10y"] <= 20]["commodity"].tolist()
print("Near 10-year highs:", ", ".join(high) or "none")
print("Near 10-year lows: ", ", ".join(low) or "none")

# %% [markdown]
# ## 3. Which commodities swing the most?
#
# Volatility here is the annualized standard deviation of monthly log price changes over the last ten years:
# roughly, the typical size of a year's move. A planner budgeting with a volatile input needs bigger buffers
# (or hedges) than one buying a stable one.

# %%
recent = wide[wide.index > latest - pd.DateOffset(years=10)]
logret = np.log(recent).diff()
vol = (logret.std() * np.sqrt(12) * 100).dropna()
vol = vol[recent.count() >= 100]  # skip series with many gaps in the decade
vol = vol.drop(index=[c for c in vol.index if c.endswith("_index")], errors="ignore").sort_values()
show = pd.concat([vol.head(8), vol.tail(12)])
fig, ax = plt.subplots(figsize=(11, 7))
ax.barh([names.get(c, c) for c in show.index], show.values, color=[C[1] if c in idn else C[0] for c in show.index])
ax.set_xlabel("Annualized volatility of monthly price changes, last 10 years (%)")
ax.set_title("The 8 calmest and 12 most volatile commodities (orange: Indonesia's key commodities)")
ax.grid(axis="y", visible=False)
plt.show()
print(f"Median volatility across {len(vol)} commodities: {vol.median():.0f}% a year.")
print("Indonesia's commodities:", ", ".join(f"{names[c]} {vol[c]:.0f}%" for c in idn if c in vol))

# %% [markdown]
# ## 4. Do Indonesia's commodities move with oil?
#
# Correlations of monthly log price changes over the last ten years. A high value means two prices tend to move
# in the same direction in the same month. Palm oil is often linked to crude oil through biodiesel and to
# soybean oil as a substitute; the matrix shows how strong those links actually are in this period.

# %%
cols = [c for c in ["crude_oil_brent", "coal_australian", "palm_oil", "soybean_oil", "coconut_oil", "rubber_tsr20",
                    "nickel", "tin", "copper", "coffee_robusta", "gold"] if c in logret]
corr = logret[cols].corr()
fig, ax = plt.subplots(figsize=(9.5, 8))
im = ax.imshow(corr, cmap="RdBu_r", vmin=-1, vmax=1)
labels = [names.get(c, c) for c in cols]
ax.set_xticks(range(len(cols)), labels, rotation=45, ha="right")
ax.set_yticks(range(len(cols)), labels)
for i in range(len(cols)):
    for j in range(len(cols)):
        ax.text(j, i, f"{corr.iloc[i, j]:.2f}", ha="center", va="center", fontsize=8,
                color="white" if abs(corr.iloc[i, j]) > 0.5 else INK)
ax.grid(False)
ax.set_title("Correlation of monthly price changes, last 10 years")
fig.colorbar(im, ax=ax, shrink=0.7)
plt.show()

pairs = corr.where(np.triu(np.ones(corr.shape, dtype=bool), 1)).stack().dropna().sort_values()
print("Strongest links:", "; ".join(f"{names[a]} & {names[b]} {v:.2f}" for (a, b), v in pairs.tail(4)[::-1].items()))
print("Weakest links:  ", "; ".join(f"{names[a]} & {names[b]} {v:.2f}" for (a, b), v in pairs.head(3).items()))
print(f"Palm oil vs Brent crude: {corr.loc['palm_oil', 'crude_oil_brent']:.2f}; "
      f"palm oil vs soybean oil: {corr.loc['palm_oil', 'soybean_oil']:.2f}")

# %% [markdown]
# ## 5. After a peak: how deep is the fall, and how long until recovery?
#
# For each of Indonesia's commodities: every month that set a new all-time high is a peak; we measure the
# deepest fall that followed before a new high, and how many months it took to get back. A commodity that is
# still below its last high has an unfinished drawdown.

# %%
rows = []
for c in idn:
    p = wide[c].dropna()
    running_max = p.cummax()
    drawdown = p / running_max - 1
    # Episodes: from a high until the price first gets back to it.
    in_dd, start, worst, last_high = False, None, 0.0, p.index[0]
    for month, d in drawdown.items():
        if d == 0 and not in_dd:
            last_high = month
        if d < 0 and not in_dd:
            in_dd, start, worst = True, last_high, d  # the episode starts at the record month
        elif in_dd:
            worst = min(worst, d)
            if d == 0:
                months = (month.year - start.year) * 12 + month.month - start.month
                rows.append({"commodity": names[c], "peak": start, "max_fall_pct": worst * 100, "months_to_recover": months})
                in_dd, last_high = False, month
    if in_dd:
        rows.append({"commodity": names[c], "peak": start, "max_fall_pct": worst * 100, "months_to_recover": np.nan})
dd = pd.DataFrame(rows)
big = dd[dd["max_fall_pct"] <= -40].sort_values(["commodity", "peak"])
print("Drawdowns of 40% or more from an all-time high (nominal):")
print(big.assign(peak=big["peak"].dt.strftime("%b %Y"), max_fall_pct=big["max_fall_pct"].round(0))
      .rename(columns={"max_fall_pct": "max fall %", "months_to_recover": "months to new high (NaN: not yet)"})
      .to_string(index=False))

# %%
fig, ax = plt.subplots()
for c, color in zip(idn, C):
    p = wide[c].dropna()
    ax.plot(p.index, (p / p.cummax() - 1) * 100, color=color, lw=1.2, label=names[c])
ax.set_title("Distance from the all-time high so far (%), Indonesia's key commodities")
ax.set_ylabel("% below the previous record")
ax.legend(ncol=3, fontsize=8.5, loc="lower left")
plt.show()

# %% [markdown]
# ## Takeaways
#
# - **Cycles are long and deep.** Even in nominal dollars, falls of 40% or more after a record are common,
#   and the table above shows how many years some took to recover. Planning on today's price is planning on
#   one point of a cycle.
# - **Indonesia's export basket is not one bet.** The correlation matrix shows which of its commodities move
#   together; the weaker the links, the more diversification the basket gives export earnings.
# - **Volatility differs by an order of magnitude**, so buffers, contracts and hedges should differ too.
#
# **Limits**: prices are nominal (deflate them for long-run comparisons), monthly averages hide intra-month
# swings, and some series changed specification over time (the dataset description lists where to check).
