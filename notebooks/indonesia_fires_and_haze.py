# %% [markdown]
# # Indonesia's fire seasons from space, and the haze they bring
#
# This notebook explores **[Indonesia Fire Hotspots (NASA FIRMS, daily)](https://www.kaggle.com/datasets/danielaijdkx/indonesia-fire-hotspots-nasa-firms)**:
# every active fire detected by the VIIRS satellites over Indonesia, with its province, updated daily.
# It joins it with **[Indonesia Air Quality](https://www.kaggle.com/datasets/danielaijdkx/indonesia-air-quality-hourly-pm25)**
# to follow fires all the way to the air people breathe.
#
# **Questions answered**
# 1. Which years had the worst fire seasons, and where does 2026 rank?
# 2. When in the year do fires happen?
# 3. Which provinces burn most?
# 4. How did the 2026 season build up, compared with earlier bad years?
# 5. When fires burn near a city, how much does its air get worse?
#
# > A detection is a 375 m pixel that was unusually hot at a satellite overpass. One fire can give
# > many detections, and cloud or thick smoke hides some fires, so counts are best used to
# > compare places and years. Trends use the **Suomi NPP** satellite only (one consistent sensor since 2012).

# %%
import glob
import os

import matplotlib.dates as mdates
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


def note(ax, x, y, text, dx=20, dy=20):
    ax.annotate(text, (x, y), xytext=(dx, dy), textcoords="offset points", fontsize=9.5, color=INK,
                arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8),
                bbox=dict(boxstyle="round,pad=0.3", fc=SURFACE, ec=GRID))


# %%
hot = pd.read_parquet(find("hotspots.parquet"))
snpp = hot[hot["satellite"] == "Suomi NPP"].copy()
snpp["year"] = snpp["acq_date"].dt.year
last_day = snpp["acq_date"].max()
print(f"{len(hot):,} detections; Suomi NPP {snpp['acq_date'].min():%Y-%m-%d} to {last_day:%Y-%m-%d}")
hot.head(3)

# %% [markdown]
# ## 1. The worst fire years
#
# Total Suomi NPP detections per year. The current year is incomplete, so it is also compared
# on a like-for-like basis: detections up to the same day of the year.

# %%
cutoff_doy = last_day.dayofyear
per_year = snpp.groupby("year").size()
to_date = snpp[snpp["acq_date"].dt.dayofyear <= cutoff_doy].groupby("year").size()
years = per_year.index[per_year.index >= snpp["year"].min() + (snpp["acq_date"].min().dayofyear > 31)]
per_year, to_date = per_year.loc[years], to_date.reindex(years).fillna(0)
top3 = per_year.drop(last_day.year, errors="ignore").nlargest(3).index

fig, ax = plt.subplots()
colors = [C[7] if y == last_day.year else (C[1] if y in top3 else MUTED) for y in per_year.index]
ax.bar(per_year.index, per_year.values, color=colors, width=0.75, label="whole year")
ax.scatter(to_date.index, to_date.values, color=INK, s=18, zorder=3,
           label=f"up to {last_day:%d %B} (same day of year)")
ax.set_title("Fire detections per year (Suomi NPP); orange: the three worst full years, red: this year")
ax.set_ylabel("detections")
ax.set_xticks(per_year.index)
ax.tick_params(axis="x", rotation=45)
ax.set_ylim(0, per_year.max() * 1.2)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
ax.legend(loc="upper right", ncol=2)
plt.show()

rank = to_date.rank(ascending=False).astype(int)
print("Worst full years:", ", ".join(f"{y} ({per_year[y]:,})" for y in top3))
print(f"{last_day.year} up to {last_day:%d %b}: {int(to_date[last_day.year]):,} detections, "
      f"rank {rank[last_day.year]} of {len(to_date)} years at the same point of the year")

# %% [markdown]
# The worst years stand far above the rest: Indonesia's fire problem is not a steady background
# but a series of catastrophic seasons. Big fire years usually follow dry conditions, such as
# El Niño years, when peatlands dry out and burn more easily. The like-for-like dots show where
# the current year ranks so far (printed above).
#
# ## 2. The fire calendar

# %%
monthly = snpp.groupby([snpp["year"], snpp["acq_date"].dt.month]).size().unstack(fill_value=0)
full_years = [y for y in monthly.index if y < last_day.year and y >= snpp["year"].min() + 1]
share = monthly.loc[full_years].sum() / monthly.loc[full_years].sum().sum()

fig, ax = plt.subplots(figsize=(11, 3.8))
months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
ax.bar(months, share.values * 100, color=[C[1] if v >= share.nlargest(3).min() else C[0] for v in share.values])
ax.set_title("Share of a year's fire detections by month (all full years)")
ax.set_ylabel("% of detections")
plt.show()
print("Busiest months:", ", ".join(f"{months[m - 1]} ({share[m]:.0%})" for m in share.nlargest(3).index))

# %% [markdown]
# Most fires burn in the dry season, peaking late in the year, before the monsoon rains put them
# out. A smaller early-year peak comes from northern Sumatra (e.g. Riau), where the dry season
# comes earlier.
#
# ## 3. Where fires burn

# %%
prov = snpp[snpp["year"].isin(full_years)].groupby("province").size().sort_values()
top = prov.tail(12)
fig, ax = plt.subplots(figsize=(11, 5.2))
ax.barh(top.index, top.values / len(full_years), color=C[1])
for y, v in enumerate(top.values / len(full_years)):
    ax.text(v, y, f" {v:,.0f}", va="center", fontsize=9, color=INK2)
ax.set_title(f"Average fire detections per year by province ({full_years[0]}-{full_years[-1]})")
ax.set_xlabel("detections per year (Suomi NPP)")
ax.grid(axis="y", visible=False)
plt.show()
print(f"The top 5 provinces account for {prov.tail(5).sum() / prov.sum():.0%} of all detections.")

# %%
sample = snpp[snpp["year"] == last_day.year]
fig, ax = plt.subplots(figsize=(11, 4.4))
hb = ax.hexbin(sample["longitude"], sample["latitude"], gridsize=160, bins="log", cmap="OrRd", mincnt=1, linewidths=0)
fig.colorbar(hb, ax=ax, shrink=0.7, label="detections per cell (log scale)")
ax.set_xlim(94, 142)
ax.set_ylim(-11.5, 6.5)
ax.set_aspect("equal")
ax.set_xticks([])
ax.set_yticks([])
ax.grid(False)
ax.set_title(f"Every fire detection in {last_day.year} so far ({len(sample):,})")
plt.show()

# %% [markdown]
# The darkest cells mark where fires concentrated: southern and central Kalimantan, eastern Sumatra,
# the savanna of Nusa Tenggara and southern Papua.
#
# ## 4. How the current season built up
#
# Cumulative detections through the year, for the current year and the three worst full years.

# %%
fig, ax = plt.subplots()
for year, color in zip(list(top3) + [last_day.year], [C[1], C[3], C[6], C[7]]):
    d = snpp[snpp["year"] == year].groupby(snpp["acq_date"].dt.dayofyear).size()
    cum = d.reindex(range(1, 367), fill_value=0).cumsum()
    if year == last_day.year:
        cum = cum.loc[:cutoff_doy]
    ax.plot(cum.index, cum.values, color=color, lw=2.6 if year == last_day.year else 1.8)
    ax.text(cum.index[-1] + 3, cum.values[-1], str(year), color=color, va="center", fontsize=10, fontweight="bold")
ax.set_title("Cumulative fire detections through the year")
ax.set_xlabel("day of year")
ax.set_ylabel("detections so far")
ax.set_xlim(1, 400)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
plt.show()

ahead = to_date[to_date > to_date[last_day.year]].index.tolist()
print(f"By {last_day:%d %B}, {last_day.year} had {int(to_date[last_day.year]):,} detections. "
      f"Years with more by the same date: {', '.join(map(str, ahead)) or 'none'}.")

# %% [markdown]
# ## 5. Fires and the air in nearby cities
#
# For cities in the fire belt, count the fires detected within **200 km** each day and compare
# with that day's PM2.5 in the city.
#
# > The PM2.5 values come from the CAMS atmospheric model (via Open-Meteo), which estimates fire
# > smoke partly from satellite fire observations. The link below is therefore partly built into
# > the model; it shows the size of the effect the model sees, not an independent measurement.

# %%
aq = pd.read_csv(find("idn_air_quality_daily.csv"), parse_dates=["date"])
cities = pd.read_csv(find("cities.csv"))
fire_cities = ["Pekanbaru", "Palembang", "Jambi", "Palangka Raya", "Pontianak", "Banjarmasin"]
fires = snpp[snpp["acq_date"] >= aq["date"].min()]


def fires_near(lat, lon, km=200):
    """Daily count of detections within `km` of a point (haversine distance)."""
    lat1, lon1 = np.radians(lat), np.radians(lon)
    lat2, lon2 = np.radians(fires["latitude"].to_numpy()), np.radians(fires["longitude"].to_numpy())
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    near = 2 * 6371 * np.arcsin(np.sqrt(a)) <= km
    return fires.loc[near].groupby("acq_date").size()


rows = []
for city in fire_cities:
    c = cities.set_index("city").loc[city]
    counts = fires_near(c["latitude"], c["longitude"])
    city_aq = aq[aq["city"] == city].set_index("date")["pm2_5_mean"]
    df = pd.DataFrame({"pm25": city_aq}).join(counts.rename("fires")).fillna({"fires": 0})
    df["city"] = city
    rows.append(df.reset_index())
joined = pd.concat(rows, ignore_index=True).dropna(subset=["pm25"])
bins = [-1, 0, 10, 50, 200, np.inf]
labels = ["0", "1-10", "11-50", "51-200", ">200"]
joined["fires nearby"] = pd.cut(joined["fires"], bins=bins, labels=labels)
table = joined.pivot_table(index="city", columns="fires nearby", values="pm25", aggfunc="median", observed=False)
table.round(0)

# %%
fig, ax = plt.subplots()
for i, city in enumerate(fire_cities):
    ax.plot(labels, table.loc[city, labels].values, marker="o", color=C[i], lw=1.8)
    ax.text(len(labels) - 1 + 0.08, table.loc[city, labels[-1]], city, color=C[i], va="center", fontsize=9.5)
ax.axhline(15, color=INK2, lw=1, ls="--")
ax.text(-0.25, 4, "dashed: WHO 24-hour guideline (15 µg/m³)", fontsize=9, color=INK2)
ax.set_title("Median daily PM2.5 by number of fires within 200 km that day")
ax.set_xlabel("fire detections within 200 km")
ax.set_ylabel("PM2.5 (µg/m³)")
ax.set_xlim(-0.3, len(labels) - 0.2)
plt.show()

clean = joined[joined["fires"] == 0].groupby("city")["pm25"].median()
smoky = joined[joined["fires"] > 200].groupby("city")["pm25"].median()
ratio = (smoky / clean).dropna()
print("PM2.5 on days with >200 fires nearby, compared with days without fires:")
print(ratio.round(1).sort_values(ascending=False).to_string())

# %% [markdown]
# In every city, the median PM2.5 on days with more than 200 fires nearby is above the WHO
# guideline and well above fire-free days, but the size of the jump differs a lot (ratios printed
# above). Palangka Raya, surrounded by Central Kalimantan's peatlands, is hit hardest; in some
# cities PM2.5 barely moves until fires become very numerous. Fire seasons are public-health
# emergencies, and fire counts are a useful input for air-quality warnings.
#
# ## Takeaways
#
# - Fire activity is dominated by a few catastrophic years; the like-for-like chart shows how the
#   current year compares.
# - Fires follow the dry season and concentrate in a handful of provinces in Kalimantan, Sumatra,
#   Nusa Tenggara and Papua.
# - Nearby fires and urban PM2.5 move together in the fire belt, most strongly in Palangka Raya
#   (with the caveat about model-based PM2.5 above).
#
# Ideas to take further: add rainfall from the
# [Indonesia weather](https://www.kaggle.com/datasets/danielaijdkx/indonesia-daily-weather-31-cities)
# dataset to model fire risk from dry spells, or use the
# [politics tracker](https://www.kaggle.com/datasets/danielaijdkx/indonesian-political-moves-database-2024-2026)
# to compare news attention to fires (`event_topics`, topic `karhutla`) with the fires themselves.
