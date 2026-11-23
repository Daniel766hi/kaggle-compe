# %% [markdown]
# # Indomaret vs Alfamart: who leads where?
#
# This notebook explores **[Indonesia Minimarkets: Indomaret vs Alfamart Map](https://www.kaggle.com/datasets/danielaijdkx/indonesia-minimarket-network-indomaret-alfamart)**,
# every convenience store and supermarket mapped in OpenStreetMap.
#
# **Questions answered**
# 1. How large are the chains on the map?
# 2. Which chain leads in each province?
# 3. How dense is the network, and where are the gaps?
# 4. How common are 24-hour stores?
#
# OpenStreetMap is mapped by volunteers, so counts are lower bounds and differ partly with mapping effort. The
# numbers in the text are computed from the data each time the notebook runs.

# %%
import glob
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

INK2, GRID, SURFACE = "#52514e", "#e6e5e0", "#fcfcfb"
CHAIN_COLORS = {"Indomaret": "#2a78d6", "Alfamart": "#e34948", "Alfamidi": "#eb6834", "Independent": "#c3c2b7"}
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


stores = pd.read_csv(find("stores.csv"))
summary = pd.read_csv(find("province_summary.csv"))
print(f"{len(stores):,} stores in {stores['province'].nunique()} provinces; "
      f"{(stores['chain'] != 'Independent').mean():.0%} matched to a chain")

# %% [markdown]
# ## 1. The chains on the map

# %%
chains = stores.loc[stores["chain"] != "Independent", "chain"].value_counts()
fig, ax = plt.subplots(figsize=(11, 5))
ax.barh(chains.index[::-1], chains.values[::-1], color=[CHAIN_COLORS.get(c, "#6250d6") for c in chains.index[::-1]])
for y, v in enumerate(chains.values[::-1]):
    ax.text(v, y, f" {v:,}", va="center", fontsize=9, color=INK2)
ax.set_xlabel("Stores mapped in OpenStreetMap"); ax.grid(axis="y", visible=False)
ax.set_title("Chain stores mapped across Indonesia")
plt.show()
ind = summary["indomaret"].sum(); alfa = summary["alfamart"].sum()
print(f"Indomaret group: {ind:,} mapped stores; Alfamart group (incl. Alfamidi, Alfa Express): {alfa:,}; ratio {ind / max(alfa, 1):.2f}.")

# %% [markdown]
# ## 2. Who leads in each province?

# %%
s = summary.sort_values("stores", ascending=True)
fig, ax = plt.subplots(figsize=(11, 10))
ax.barh(s["province"], s["indomaret"], color=CHAIN_COLORS["Indomaret"], label="Indomaret group")
ax.barh(s["province"], s["alfamart"], left=s["indomaret"], color=CHAIN_COLORS["Alfamart"], label="Alfamart group")
ax.barh(s["province"], s["other_chains"], left=s["indomaret"] + s["alfamart"], color="#6250d6", label="Other chains")
ax.set_xlabel("Chain stores mapped"); ax.grid(axis="y", visible=False); ax.legend()
ax.set_title("Chain stores by province (sorted by all mapped stores)")
plt.show()
lead = summary.dropna(subset=["indomaret_vs_alfamart"])
print(f"Indomaret leads in {(lead['indomaret_vs_alfamart'] > 1).sum()} provinces, Alfamart in "
      f"{(lead['indomaret_vs_alfamart'] < 1).sum()}, tied in {(lead['indomaret_vs_alfamart'] == 1).sum()}.")
print(lead.sort_values("indomaret_vs_alfamart")[["province", "indomaret", "alfamart", "indomaret_vs_alfamart"]]
      .iloc[[0, 1, 2, -3, -2, -1]].to_string(index=False))

# %% [markdown]
# ## 3. Where the network is dense, and where the map is empty
#
# Each dot is a mapped store. Dense clusters are both store density and mapping effort; empty areas can be either
# truly unserved or simply unmapped.

# %%
fig, ax = plt.subplots(figsize=(13, 5.5))
for chain, color in CHAIN_COLORS.items():
    d = stores[stores["chain"] == chain] if chain != "Independent" else stores[~stores["chain"].isin(list(CHAIN_COLORS)[:3])]
    ax.scatter(d["longitude"], d["latitude"], s=1.5 if chain == "Independent" else 2.5, color=color, alpha=0.5,
               label=chain if chain != "Independent" else "Other / independent")
ax.set_xlim(94.5, 141.5); ax.set_ylim(-11.5, 6.5); ax.set_aspect("equal")
ax.set_title("Mapped stores across Indonesia"); ax.legend(markerscale=6, loc="lower left")
plt.show()
java = stores["province"].isin(["DKI Jakarta", "Banten", "Jawa Barat", "Jawa Tengah", "DI Yogyakarta", "Jawa Timur"])
print(f"{java.mean():.0%} of mapped stores are on Java.")

# %% [markdown]
# ## 4. How many stores are open 24 hours?

# %%
has_hours = stores["opening_hours"].notna()
h = stores[has_hours].assign(is_24_7=lambda d: d["opening_hours"].str.strip().eq("24/7"))
share = h.groupby("chain")["is_24_7"].agg(["mean", "size"])
share = share[share["size"] >= 30].sort_values("mean", ascending=False)
print(f"{has_hours.mean():.0%} of stores have opening hours mapped. Share open 24/7 among those (chains with 30+ mapped hours):")
print((share["mean"] * 100).round(0).astype(int).astype(str).add("%").to_string())

# %% [markdown]
# ## Takeaways
#
# - The two big minimarket groups dominate the chain stores on the map; section 2 shows which leads where.
# - Mapped density follows Java and the big cities, partly because that is where mapping is densest.
# - Opening-hours tags are sparse, so the 24/7 shares rest on the stores where someone mapped hours.
#
# **Limits**: OpenStreetMap is incomplete and uneven; compare chain shares within a province rather than raw
# totals between provinces, and treat growth over time as new stores plus newly mapped ones.
