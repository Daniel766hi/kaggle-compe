# %% [markdown]
# # Who gets into the museum? 730,000 artworks from MoMA, the Met and Cleveland
#
# This notebook explores **[Art Museum Collections: MoMA, Met, Cleveland](https://www.kaggle.com/datasets/danielaijdkx/art-museum-collections-moma-met-cleveland)**:
# the full open-access collections of three great museums in one table, updated weekly.
#
# **Questions answered**
# 1. What do the three museums hold, and from when?
# 2. Which artists and nationalities dominate each collection?
# 3. How much art by women do museums collect, and is that changing?
# 4. What is actually on view?
# 5. How fast do the collections grow?

# %%
import glob
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

INK, INK2, GRID, SURFACE, MUTED = "#0b0b0b", "#52514e", "#e6e5e0", "#fcfcfb", "#c3c2b7"
C = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
MUSEUM_COLORS = {"MoMA": C[7], "The Met": C[0], "Cleveland Museum of Art": C[2]}
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
art = pd.read_parquet(find("artworks.parquet"))
acq = pd.read_csv(find("acquisitions_by_year.csv"))
artists = pd.read_csv(find("artists.csv"))
summary = art.groupby("museum").agg(
    objects=("object_id", "size"), named_artists=("artist", "nunique"),
    on_view=("on_view", "sum"), oldest=("year_start", "min"), newest=("year_end", "max"))
summary["on_view_share"] = (summary["on_view"] / summary["objects"]).round(3)
summary

# %% [markdown]
# ## 1. From when? Five thousand years of objects
#
# The Met and Cleveland are encyclopedic: ancient Egypt, Greece, China, the Americas. MoMA collects from
# the 1880s onward. (Years before 0 are BCE; the horizontal axis is stretched for recent centuries.)

# %%
bins = [-8000, -3000, -1000, 0, 500, 1000, 1300, 1500, 1600, 1700, 1800, 1850, 1900, 1950, 2000, 2030]
labels = ["before 3000 BCE", "3000-1000 BCE", "1000 BCE-0", "0-500", "500-1000", "1000-1300", "1300-1500",
          "1500s", "1600s", "1700s", "1800-49", "1850-99", "1900-49", "1950-99", "2000+"]
art["period"] = pd.cut(art["year_start"], bins, labels=labels, right=False)
by_period = art.groupby(["period", "museum"], observed=False).size().unstack(fill_value=0)
fig, ax = plt.subplots(figsize=(12, 4.8))
left = np.zeros(len(by_period))
for museum in ["The Met", "Cleveland Museum of Art", "MoMA"]:
    ax.barh(by_period.index.astype(str), by_period[museum], left=left, color=MUSEUM_COLORS[museum], label=museum)
    left += by_period[museum].to_numpy()
ax.invert_yaxis()
ax.set_xlabel("Objects")
ax.set_title("When the objects were made")
ax.grid(axis="y", visible=False)
ax.legend(loc="upper right")
plt.show()

# %% [markdown]
# ## 2. Who and where from?

# %%
top = (art.dropna(subset=["artist"]).groupby(["museum", "artist"]).size().rename("works").reset_index()
       .sort_values(["museum", "works"], ascending=[True, False]).groupby("museum").head(8))
top["rank"] = top.groupby("museum").cumcount() + 1
top.assign(artist=top["artist"] + " (" + top["works"].map("{:,}".format) + ")").pivot(
    index="rank", columns="museum", values="artist")

# %% [markdown]
# The top names are often archives or photographers with thousands of prints (Mies van der Rohe's
# architectural drawings at MoMA, Walker Evans at the Met) and, at the Met, makers of 19th-century
# tobacco trading cards. Counting **artists** instead of works gives a fairer picture of breadth:

# %%
nat = art.dropna(subset=["artist", "artist_nationality"]).drop_duplicates(["museum", "artist"])
nat_share = (nat.groupby(["museum", "artist_nationality"]).size()
             / nat.groupby("museum").size()).rename("share of artists").reset_index()
nat_top = nat_share.sort_values("share of artists", ascending=False).groupby("museum").head(6)
nat_top.assign(**{"share of artists": nat_top["share of artists"].map("{:.0%}".format)}) \
    .assign(rank=lambda d: d.groupby("museum").cumcount() + 1) \
    .assign(cell=lambda d: d["artist_nationality"] + " " + d["share of artists"]) \
    .pivot(index="rank", columns="museum", values="cell")

# %% [markdown]
# ## 3. Art by women
#
# MoMA and Cleveland record each artist's gender (the Met records only *female*, so it is left out
# here). Below: the share of acquired works whose first artist is a woman, per decade of acquisition.

# %%
a = acq[acq["museum"] != "The Met"].copy()
a["decade"] = a["year"] // 10 * 10
dec = a.groupby(["museum", "decade"])[["works_by_women", "works_gender_known"]].sum()
dec["share"] = dec["works_by_women"] / dec["works_gender_known"]
dec = dec[dec["works_gender_known"] >= 200].reset_index()
fig, ax = plt.subplots()
for museum, g in dec.groupby("museum"):
    ax.plot(g["decade"], g["share"] * 100, marker="o", color=MUSEUM_COLORS[museum], label=museum)
ax.set_ylabel("% of acquired works by women")
ax.set_xlabel("Decade of acquisition")
ax.set_title("Museums now acquire far more work by women than they used to")
ax.legend()
plt.show()
overall = art[art["museum"] != "The Met"].groupby("museum")["artist_gender"].apply(
    lambda s: (s == "female").sum() / s.notna().sum())
print("Share of works by women in the whole collection:", overall.map("{:.0%}".format).to_dict())
print("Last full decade:", dec[dec["decade"] == 2010].set_index("museum")["share"].map("{:.0%}".format).to_dict())

# %% [markdown]
# ## 4. What is on view?
#
# A museum shows only a small part of what it owns. On-view share by department (departments with at
# least 2,000 objects):

# %%
dept = art.groupby(["museum", "department"]).agg(objects=("object_id", "size"), on_view=("on_view", "mean"))
dept = dept[dept["objects"] >= 2000].reset_index().sort_values("on_view", ascending=False)
dept.assign(on_view=(dept["on_view"] * 100).round(1)).rename(columns={"on_view": "% on view"}).head(15) \
    .reset_index(drop=True)

# %% [markdown]
# ## 5. How fast do the collections grow?

# %%
fig, ax = plt.subplots()
for museum, g in acq[acq["year"] >= 1930].groupby("museum"):
    ax.plot(g["year"], g["works"].rolling(5, min_periods=1).mean(), color=MUSEUM_COLORS[museum], label=museum)
ax.set_yscale("log")
ax.set_ylabel("Works acquired per year (5-year average)")
ax.set_title("Acquisitions per year, by museum")
ax.legend()
plt.show()

# %% [markdown]
# The `collection_snapshots` table adds one row per museum each week (objects, on view, public domain),
# so week-to-week growth becomes visible as the dataset updates.
#
# ## Takeaways
#
# - The Met and Cleveland span five millennia; MoMA concentrates on the last 140 years.
# - Collections are dominated by Americans and Europeans, with a few prolific photographers and archives.
# - Women's share of acquisitions rose from a few percent before 1970 to about a quarter in the 2010s
#   at MoMA, but women made only 14% (MoMA) and 10% (Cleveland) of the works in the collections.
# - Less than a tenth of each collection is on view (MoMA's file marks only about 1% as on view).
#
# Data: MoMA, The Metropolitan Museum of Art and the Cleveland Museum of Art open-access data (CC0).
