# %% [markdown]
# # Indonesia's earthquakes: where, how big, and what comes after
#
# This notebook explores **[Indonesia Earthquakes since 1900 (USGS, daily)](https://www.kaggle.com/datasets/danielaijdkx/indonesia-earthquakes-usgs-daily)**:
# every earthquake the U.S. Geological Survey has catalogued in and around Indonesia, with the
# nearest province of each epicentre, updated daily.
#
# **Questions answered**
# 1. Where do Indonesia's earthquakes happen, and how deep?
# 2. Which provinces get the most strong quakes?
# 3. How often do large quakes happen, and is that changing?
# 4. How rare are big ones? (the Gutenberg-Richter law)
# 5. What follows a large quake: how many aftershocks, and for how long?
#
# > A global catalogue records Indonesia's quakes completely only from about magnitude 4.5 (since
# > about 1990), so counts below use M4.5+ from 1990 or higher magnitudes for older years.

# %%
import glob
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

INK, INK2, GRID, SURFACE, MUTED = "#0b0b0b", "#52514e", "#e6e5e0", "#fcfcfb", "#c3c2b7"
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
eq = pd.read_csv(find("earthquakes.csv"), parse_dates=["time", "time_wib", "updated"], low_memory=False)
quakes = eq[eq["type"] == "earthquake"].copy()
idn = quakes[quakes["country"] == "Indonesia"].copy()
idn["year"] = idn["time"].dt.year
print(f"{len(eq):,} events in the box, {len(idn):,} earthquakes nearest Indonesia, "
      f"{eq['time'].min():%Y} to {eq['time'].max():%d %B %Y}")
print(f"M4.5+ since 1990: {((idn['mag'] >= 4.5) & (idn['year'] >= 1990)).sum():,}; "
      f"M7+ since 1900: {(idn['mag'] >= 7).sum():,}")

# %% [markdown]
# ## 1. Where, and how deep
#
# Each dot is an M5+ quake since 1973, coloured by depth. The shapes are the plate boundaries: the
# Sunda megathrust off Sumatra and Java, the deep slab dipping north under Java and the Banda Sea,
# and the tangle of plates around Sulawesi, Maluku and Papua.

# %%
big = quakes[(quakes["mag"] >= 5) & (quakes["time"] >= "1973-01-01")].sort_values("depth_km", ascending=False)
bands = [(0, 70, "shallow (< 70 km)", C[7]), (70, 300, "intermediate (70-300 km)", C[3]),
         (300, 800, "deep (300+ km)", C[0])]
fig, ax = plt.subplots(figsize=(12, 5.8))
for lo, hi, label, color in bands:
    b = big[(big["depth_km"] >= lo) & (big["depth_km"] < hi)]
    ax.scatter(b["longitude"], b["latitude"], s=(b["mag"] - 4.5) ** 2.5 * 6, color=color, alpha=0.45,
               lw=0, label=f"{label}: {len(b):,}")
ax.set_aspect("equal")
ax.set_xlim(93.5, 142.5)
ax.set_ylim(-12.5, 7.5)
ax.set_title("M5+ earthquakes since 1973, by depth (size = magnitude)")
ax.legend(loc="lower left", markerscale=0.8)
plt.show()

# %% [markdown]
# ## 2. Which provinces shake most
#
# Offshore quakes are counted for the nearest province, so coastal provinces facing the megathrust
# collect many.

# %%
recent = idn[(idn["year"] >= 1990) & (idn["mag"] >= 5)]
by_prov = recent.groupby("province").agg(m5=("mag", "size"), m6=("mag", lambda m: int((m >= 6).sum())),
                                         m7=("mag", lambda m: int((m >= 7).sum())), largest=("mag", "max"))
by_prov = by_prov.sort_values("m5", ascending=True).tail(15)
fig, ax = plt.subplots(figsize=(11, 6))
ax.barh(by_prov.index, by_prov["m5"], color=C[0], label="M5+")
ax.barh(by_prov.index, by_prov["m6"], color=C[7], label="of which M6+")
for y, (n, m) in enumerate(zip(by_prov["m5"], by_prov["largest"])):
    ax.text(n + 5, y, f"largest M{m:.1f}", va="center", fontsize=9, color=INK2)
ax.set_title("Provinces with the most M5+ earthquakes since 1990 (nearest province)")
ax.grid(axis="y", visible=False)
ax.legend(loc="lower right")
plt.show()

# %% [markdown]
# ## 3. How often do large quakes happen?

# %%
yearly = idn[idn["year"] >= 1973].groupby("year")["mag"].agg(
    m6=lambda m: int((m >= 6).sum()), m7=lambda m: int((m >= 7).sum()))
yearly = yearly.reindex(range(1973, int(idn["year"].max()) + 1), fill_value=0)
fig, ax = plt.subplots()
ax.bar(yearly.index, yearly["m6"], color=C[0], label="M6+")
ax.bar(yearly.index, yearly["m7"], color=C[7], label="M7+")
ax.axhline(yearly["m6"].mean(), color=INK2, lw=1, ls="--")
top = yearly["m6"].idxmax()
ax.annotate(f"{top}: {yearly.loc[top, 'm6']} quakes of M6+", (top, yearly.loc[top, "m6"]), xytext=(-150, -5),
            textcoords="offset points", fontsize=9.5, arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
ax.set_title(f"M6+ earthquakes per year (dashed: average {yearly['m6'].mean():.0f} a year)")
ax.legend(loc="upper left")
plt.show()
print("Last 5 years:", yearly.tail(5)["m6"].to_dict())

# %% [markdown]
# The busiest stretch, 2004-2009, came with the great Sumatra quakes (Aceh 2004 M9.1, Nias 2005
# M8.6, Bengkulu 2007 M8.4) and their aftershocks. Outside it, a typical year has 10 to 20 M6+
# quakes, with no sign of a steady long-term rise.
#
# ## 4. How rare are big ones? The Gutenberg-Richter law
#
# The number of quakes at least as large as M falls about tenfold per magnitude unit. The slope
# (the *b-value*) is estimated here with Aki's maximum-likelihood formula for M4.5+ since 1990.

# %%
m = idn.loc[(idn["year"] >= 1990) & (idn["mag"] >= 4.5), "mag"]
mc, dm = 4.5, 0.1
b = np.log10(np.e) / (m.mean() - (mc - dm / 2))
years = idn["year"].max() - 1990 + 1
grid = np.arange(4.5, m.max() + 0.05, 0.1)
per_year = np.array([(m >= g - 1e-9).sum() for g in grid]) / years
a = np.log10(per_year[0]) + b * mc
fig, ax = plt.subplots()
ax.semilogy(grid, per_year, "o", ms=4, color=C[0], label="observed")
ax.semilogy(grid, 10 ** (a - b * grid), color=C[7], lw=1.5, label=f"log10 N = {a:.2f} - {b:.2f} M")
ax.set_xlabel("Magnitude M")
ax.set_ylabel("Quakes of at least M per year")
ax.set_title(f"Gutenberg-Richter: b = {b:.2f}")
ax.legend()
plt.show()
# Long-run rates counted directly (M8+ since 1900, as such quakes are rare but always recorded).
for mag, since in ((6, 1990), (7, 1990), (8, 1900)):
    n = ((idn["mag"] >= mag) & (idn["year"] >= since)).sum()
    rate = n / (idn["year"].max() - since + 1)
    every = f"about {rate:.0f} a year" if rate >= 1.5 else f"one every {1 / rate:.1f} years on average"
    print(f"M{mag}+ since {since}: {n} quakes, {every}")

# %% [markdown]
# The line fits well up to about M6.5. Quakes of M6.5-8 are somewhat more frequent than the line
# predicts (common in subduction zones), so the long-run rates above are counted directly, not
# read off the line.
#
# ## 5. What comes after a large quake
#
# The `aftershock_sequences` table lists every M5.5+ quake since 1990 with the M4.5+ quakes that
# followed within its rupture zone. Aftershock productivity grows about tenfold per magnitude
# unit, and shallow quakes are far more productive than deep ones.

# %%
seq = pd.read_csv(find("aftershock_sequences.csv"), parse_dates=["time"])
s = seq[(seq["country"] == "Indonesia") & seq["complete_7d"] & ~seq["prior_larger_30d"]].copy()
s["mag_bin"] = (s["mag"] * 2).round() / 2
s["depth_class"] = np.where(s["depth_km"] < 70, "shallow (< 70 km)", "deeper (70+ km)")
prod = s.groupby(["depth_class", "mag_bin"])["aftershocks_m45_7d"].agg(["mean", "size"]).reset_index()
prod = prod[prod["size"] >= 5]
fig, ax = plt.subplots()
for (name, g), color in zip(prod.groupby("depth_class"), [C[0], C[7]]):
    ax.semilogy(g["mag_bin"], g["mean"].clip(lower=0.01), "o-", color=color, label=name)
ax.set_xlabel("Mainshock magnitude (rounded to 0.5)")
ax.set_ylabel("Mean M4.5+ aftershocks in 7 days")
ax.set_title("Aftershock productivity grows with magnitude, and is higher for shallow quakes")
ax.legend()
plt.show()

# %% [markdown]
# Most aftershocks come in the first hours and days: the rate decays roughly as 1/time (the Omori
# law). Below, all M4.5+ aftershocks of independent M6.5+ shallow quakes, by hour after the mainshock.
# In the first hour the curve flattens: right after a big quake, seismic waves overlap and many
# aftershocks go uncatalogued, so the fit uses the time after the first hour.

# %%
mains = s[(s["mag"] >= 6.5) & (s["depth_km"] < 70)]
q = quakes[quakes["mag"] >= 4.5][["time", "latitude", "longitude"]]
t_all = q["time"].to_numpy()
hours = []
for r in mains.itertuples():
    w = q[(q["time"] > r.time) & (q["time"] <= r.time + pd.Timedelta(days=30))]
    lat1, lon1, lat2, lon2 = map(np.radians, (r.latitude, r.longitude, w["latitude"], w["longitude"]))
    d = 6371 * 2 * np.arcsin(np.sqrt(np.sin((lat2 - lat1) / 2) ** 2
                                     + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2))
    hours += list(((w["time"] - r.time).dt.total_seconds() / 3600)[d <= r.radius_km])
hours = np.array(hours)
edges = np.logspace(-1, np.log10(30 * 24), 25)
counts, _ = np.histogram(hours, edges)
rate = counts / np.diff(edges) / len(mains)
mid = np.sqrt(edges[1:] * edges[:-1])
fig, ax = plt.subplots()
ax.loglog(mid, rate, "o", color=C[0], label="observed")
ok = rate > 0
slope, icpt = np.polyfit(np.log10(mid[ok & (mid > 1)]), np.log10(rate[ok & (mid > 1)]), 1)
ax.loglog(mid[mid > 1], 10 ** icpt * mid[mid > 1] ** slope, color=C[7], lw=1.5, label=f"fit after 1 h: rate ~ t^{slope:.2f}")
ax.set_xlabel("Hours after the mainshock")
ax.set_ylabel("Aftershocks per hour, per sequence")
ax.set_title(f"Omori's law in {len(mains)} Indonesian sequences (M6.5+, shallow)")
ax.legend()
plt.show()
share = (hours <= 24).mean()
print(f"{share:.0%} of the first month's M4.5+ aftershocks came within 24 hours; "
      f"{(hours <= 24 * 7).mean():.0%} within the first week.")

# %% [markdown]
# ## The largest earthquakes in the catalogue

# %%
cols = ["time_wib", "mag", "mag_type", "depth_km", "province", "place"]
idn.nlargest(15, "mag")[cols].reset_index(drop=True)

# %% [markdown]
# ## Takeaways
#
# - Indonesia's quakes trace its plate boundaries: shallow ones along the Sunda trench and in the
#   east, and deep ones under Java, Flores and the Banda Sea, down to about 650 km.
# - Large quakes come at a roughly steady rate; the busiest years, 2004-2009, followed the great
#   Sumatra quakes.
# - The Gutenberg-Richter law holds well up to about M6.5; larger quakes are a little more frequent
#   than it predicts (about two M7+ quakes a year, and an M8+ every decade or so).
# - Aftershocks follow simple laws: more after bigger and shallower quakes, most within the first day.
#   The [Indonesia Aftershock Forecast model](https://www.kaggle.com/models/danielaijdkx/indonesia-aftershock-forecast)
#   turns these patterns into a 7-day forecast.
#
# Data: U.S. Geological Survey ANSS Comprehensive Catalog (public domain); province outlines from
# geoBoundaries (CC BY 4.0).
