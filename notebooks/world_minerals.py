# %% [markdown]
# # Indonesia on the critical minerals map
#
# This notebook explores **[World Mineral Production & Reserves (USGS)](https://www.kaggle.com/datasets/danielaijdkx/world-mineral-production-reserves-usgs)**,
# the U.S. Geological Survey's Mineral Commodity Summaries.
#
# **Questions answered**
# 1. How concentrated is world mine production, mineral by mineral?
# 2. Where does Indonesia rank, and in which minerals is it a top-3 producer?
# 3. How many years of production do reserves cover, country by country, for nickel and tin?
# 4. Which countries hold the reserves of critical minerals?
#
# The numbers in the text are computed from the data each time the notebook runs.

# %%
import glob
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

INK2, GRID, SURFACE = "#52514e", "#e6e5e0", "#fcfcfb"
plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE, "axes.edgecolor": GRID,
    "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "axes.grid": True, "grid.color": GRID,
    "axes.axisbelow": True, "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
    "axes.titlesize": 13, "axes.titleweight": "bold", "axes.titlelocation": "left", "font.size": 10.5,
    "figure.figsize": (11, 4.6), "figure.dpi": 110, "legend.frameon": False,
})


def find(name):
    for root in ("/kaggle/input", os.environ.get("DATA_ROOT", "../input")):
        hits = glob.glob(f"{root}/**/{name}", recursive=True)
        if hits:
            return hits[0]
    raise FileNotFoundError(name)


prod = pd.read_csv(find("world_production.csv"))
leaders = pd.read_csv(find("commodity_leaders.csv"))
ed = prod["edition"].max()
p = prod[prod["edition"] == ed]
print(f"Edition {ed}: {p['commodity'].nunique()} commodities, {p['country'].nunique()} countries, years {sorted(p['year'].unique())}")

# %% [markdown]
# ## 1. How concentrated is mine production?
#
# Share of world mine production held by the top three countries, for minerals with a published world total.

# %%
mine = leaders[(leaders["statistic"] == "Production") & leaders["detail"].str.contains("ine production", case=False)
               & leaders["top3_share_pct"].notna()].sort_values("top3_share_pct")
mine = mine[mine["top3_share_pct"] <= 100]
show = pd.concat([mine.head(8), mine.tail(17)])
fig, ax = plt.subplots(figsize=(11, 8))
ax.barh(show["commodity"], show["top3_share_pct"], color=["#e34948" if c else "#2a78d6" for c in show["is_critical"]])
for y, (v, top) in enumerate(zip(show["top3_share_pct"], show["top_country"])):
    ax.text(v + 1, y, f"{v:.0f}%  (leader: {top})", va="center", fontsize=8.5, color=INK2)
ax.set_xlim(0, 135); ax.set_xlabel("Top-3 countries' share of world mine production (%)"); ax.grid(axis="y", visible=False)
ax.set_title("Most and least concentrated minerals (red: U.S. critical mineral)")
plt.show()
print(f"Median top-3 share: {mine['top3_share_pct'].median():.0f}%. "
      f"{(mine['top_share_pct'] >= 50).sum()} minerals have a single country above 50%.")

# %% [markdown]
# ## 2. Indonesia's rankings

# %%
idn = leaders[leaders["indonesia_rank"].notna()].copy()
idn["indonesia_rank"] = idn["indonesia_rank"].astype(int)
top3 = idn[idn["indonesia_rank"] <= 3].sort_values(["statistic", "indonesia_rank"])
print(top3[["commodity", "statistic", "detail", "year", "indonesia_rank", "indonesia_share_pct", "top_country"]]
      .to_string(index=False))
print(f"\nIndonesia appears in {idn['commodity'].nunique()} commodities' tables and is top-3 in "
      f"{top3['commodity'].nunique()} of them.")

# %% [markdown]
# ## 3. Reserve life: years of production the reserves cover
#
# Reserves divided by latest mine production, by country, for nickel and tin. A static ratio: reserves grow with
# exploration and prices, so this is a pressure indicator, not a forecast of when mines run out.

# %%
def reserve_life(commodity):
    d = p[p["commodity"] == commodity]
    prodn = d[(d["statistic"] == "Production") & d["detail"].str.contains("ine production", case=False)]
    prodn = prodn[prodn["year"] == prodn["year"].max()].set_index("country")["value"]
    res = d[d["statistic"] == "Reserves"].set_index("country")["value"]
    out = pd.DataFrame({"production": prodn, "reserves": res}).dropna()
    out = out[(out["production"] > 0) & ~out.index.str.startswith(("World", "Other"))]
    return (out["reserves"] / out["production"]).sort_values()


fig, axes = plt.subplots(1, 2, figsize=(12, 5))
for ax, commodity in zip(axes, ["Nickel", "Tin"]):
    life = reserve_life(commodity)
    if life.empty:
        ax.set_visible(False)
        continue
    ax.barh(life.index, life.values, color=["#eb6834" if c == "Indonesia" else "#2a78d6" for c in life.index])
    ax.set_title(f"{commodity}: reserves / production (years)"); ax.grid(axis="y", visible=False)
    if "Indonesia" in life:
        print(f"{commodity}: Indonesia's reserves cover {life['Indonesia']:.0f} years of its current mine output.")
plt.tight_layout()
plt.show()

# %% [markdown]
# ## 4. Who holds the reserves of critical minerals?

# %%
res = leaders[(leaders["statistic"] == "Reserves") & leaders["is_critical"] & leaders["top_share_pct"].notna()]
res = res.sort_values("top_share_pct", ascending=False).head(15)
print(res[["commodity", "top_country", "top_share_pct", "top3_share_pct", "indonesia_rank"]].round(1).to_string(index=False))

# %% [markdown]
# ## Takeaways
#
# - Many minerals are produced by just a few countries; the red bars in section 1 are on the U.S. critical list.
# - Section 2 lists where Indonesia is a top-3 producer or reserve holder, nickel above all.
# - Reserve life differs widely between countries mining the same mineral.
#
# **Limits**: the latest year is an estimate; USGS withholds some company data (W) and gives some reserves only as
# words or ranges, which are left out of the numeric comparisons.
