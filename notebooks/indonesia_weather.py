# %% [markdown]
# # Indonesia's climate in 31 cities: three rain regimes, rising heat
#
# This notebook explores **[Indonesia Daily Weather: 31 Cities](https://www.kaggle.com/datasets/danielaijdkx/indonesia-daily-weather-31-cities)**,
# a daily-updated dataset of temperature, rainfall, wind and sunshine from Banda Aceh to Jayapura.
#
# **Questions answered**
# 1. Does all of Indonesia have the same rainy season? (No, there are three distinct patterns.)
# 2. Which cities are the wettest and driest?
# 3. Is Indonesia getting hotter?
# 4. A practical recipe: how likely is rain on a given day, by month? (useful for logistics, events
#    and agriculture planning)
#
# > Values come from weather reanalysis models (a grid of about 9-25 km), not from a single
# > station. They are consistent across cities and years, which makes them good for comparisons
# > and trends.

# %%
import glob
import os

import matplotlib.pyplot as plt
import matplotlib.transforms as mtransforms
from matplotlib.ticker import MaxNLocator
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
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def find(name):
    """Locate a dataset file on Kaggle (/kaggle/input) or locally (DATA_ROOT)."""
    for root in ("/kaggle/input", os.environ.get("DATA_ROOT", "../input")):
        hits = glob.glob(f"{root}/**/{name}", recursive=True)
        if hits:
            return hits[0]
    raise FileNotFoundError(name)


def label_ends(ax, items):
    """Direct labels at line ends, nudged apart so they never overlap. items: (series, text, color)."""
    trans = mtransforms.offset_copy(ax.transData, fig=ax.figure, x=8, y=0, units="points")
    lo, hi = ax.get_ylim()
    gap, placed = (hi - lo) * 0.05, []
    ends = [(s.dropna().index[-1], s.dropna().iloc[-1], t, c) for s, t, c in items]
    for x, y, text, color in sorted(ends, key=lambda e: e[1]):
        y_text = max(y, placed[-1] + gap) if placed else y
        placed.append(y_text)
        ax.plot(x, y, "o", color=color, ms=5, zorder=3)
        ax.text(x, y_text, text, transform=trans, va="center", color=INK, fontsize=9.5)


# %%
daily = pd.read_csv(find("idn_weather_daily.csv"), parse_dates=["date"])
daily["year"], daily["month"] = daily["date"].dt.year, daily["date"].dt.month

# Trends need the same cities every year: keep years where all 31 cities have (almost) every day.
days_per_city = daily.groupby(["year", "city"]).size().unstack(fill_value=0)
complete_years = days_per_city.index[(days_per_city >= 360).all(axis=1)]
full = daily[daily["year"].isin(complete_years)]
print(f"{daily['city'].nunique()} cities, {daily['date'].min():%Y-%m-%d} to {daily['date'].max():%Y-%m-%d}")
print(f"Complete years used for trends: {complete_years.min()}-{complete_years.max()} ({len(complete_years)} years)")
daily.head()

# %% [markdown]
# ## 1. Three different rainy seasons
#
# Indonesia sits on the equator, between two continents and two oceans, so "the rainy season"
# depends a lot on where you are. Four cities show the main patterns (average rainfall per month):

# %%
picks = ["Jakarta", "Kupang", "Padang", "Ambon"]
monthly_rain = (full[full["city"].isin(picks)]
                .groupby(["city", "year", "month"])["precipitation_sum"].sum()
                .groupby(["city", "month"]).mean().unstack("city"))

fig, ax = plt.subplots()
for i, city in enumerate(picks):
    ax.plot(monthly_rain.index, monthly_rain[city], color=C[i], marker="o", ms=4, label=city)
ax.set_xticks(range(1, 13), MONTHS)
ax.set_ylim(bottom=0)
ax.set_title("Average monthly rainfall: four cities, four patterns")
ax.set_ylabel("Rain per month, mm")
ax.legend(loc="upper center", ncols=4)
plt.tight_layout()
plt.show()
monthly_rain.round(0).T

# %% [markdown]
# - **Monsoon pattern (Jakarta, Kupang):** wet from November to March, dry from June to September.
#   Kupang (Nusa Tenggara Timur) is extreme: almost no rain at all in the dry months.
# - **Wet all year (Padang):** on Sumatra's west coast, rain falls in every month, with the most
#   from October to December.
# - **Reversed pattern (Ambon):** in Maluku, the wettest months are around **May to July**, exactly
#   when Java is dry.
#
# ## 2. Wettest and driest cities

# %%
annual = full.groupby(["city", "year"])["precipitation_sum"].sum().groupby("city").mean().sort_values()
fig, ax = plt.subplots(figsize=(11, 8))
ax.barh(annual.index, annual.values, color=C[0], height=0.7)
for y, v in enumerate(annual.values):
    ax.text(v + 40, y, f"{v:,.0f}", va="center", fontsize=8.5, color=INK2)
ax.set_title(f"Average yearly rainfall, {complete_years.min()}-{complete_years.max()}")
ax.set_xlabel("mm per year")
ax.grid(axis="y", visible=False)
plt.tight_layout()
plt.show()
print(f"The wettest city gets {annual.iloc[-1] / annual.iloc[0]:.1f}x the rain of the driest.")

# %% [markdown]
# The east (Kupang, Mataram) and parts of Java (Surabaya) are much drier than Sumatra's west coast,
# Papua and Maluku.
#
# ## 3. Is Indonesia getting hotter?
#
# The average of all 31 cities' daily mean temperature, per year, with a straight-line trend:

# %%
national = full.groupby("year")["temperature_2m_mean"].mean()
slope, intercept = np.polyfit(national.index, national.values, 1)

fig, ax = plt.subplots()
ax.plot(national.index, national.values, color=C[1], marker="o", ms=5, label="31-city average")
ax.plot(national.index, intercept + slope * national.index, color=INK2, lw=1, ls="--", label="linear trend")
ax.set_title(f"Average temperature across 31 cities: about +{slope * 10:.2f} °C per decade")
ax.xaxis.set_major_locator(MaxNLocator(integer=True))
ax.set_ylabel("°C")
ax.legend(loc="upper left")
plt.tight_layout()
plt.show()
print("Warmest years:", ", ".join(f"{y} ({t:.2f} °C)" for y, t in national.nlargest(4).items()))

# %% [markdown]
# Year-to-year swings are large (El Niño years such as 2015-16 and 2023-24 tend to be warmer), but
# the trend is upward and the warmest years are recent ones.
#
# **Very hot days** tell the same story. Here is the share of all city-days with a maximum
# temperature of 35 °C or more:

# %%
hot = full.assign(hot=full["temperature_2m_max"] >= 35).groupby("year")["hot"].mean() * 100
fig, ax = plt.subplots()
ax.bar(hot.index, hot.values, color=C[1], width=0.7)
ax.set_title("Share of city-days reaching 35 °C or more")
ax.xaxis.set_major_locator(MaxNLocator(integer=True))
ax.set_ylabel("% of city-days")
ax.grid(axis="x", visible=False)
plt.tight_layout()
plt.show()
print("Cities with the most 35 °C+ days:")
full[full["temperature_2m_max"] >= 35].groupby("city").size().nlargest(5).rename("days").to_frame().T

# %% [markdown]
# ## 4. Recipe: chance of rain by month
#
# For planning outdoor work, deliveries, construction or events, a simple and useful number is the
# **probability that a given day has at least 1 mm of rain**, by city and month:

# %%
rain_prob = (full.assign(rainy=full["precipitation_sum"] >= 1)
             .pivot_table(index="city", columns="month", values="rainy", aggfunc="mean") * 100)
rain_prob.columns = MONTHS

fig, ax = plt.subplots(figsize=(11, 9))
im = ax.imshow(rain_prob.values, cmap="Blues", vmin=0, vmax=100, aspect="auto")
ax.set_xticks(range(12), MONTHS)
ax.set_yticks(range(len(rain_prob)), rain_prob.index)
ax.grid(False)
for (r, c), v in np.ndenumerate(rain_prob.values):
    ax.text(c, r, f"{v:.0f}", ha="center", va="center", fontsize=7.5, color=INK if v < 60 else SURFACE)
ax.set_title("Chance of a rainy day (≥ 1 mm), % by month")
fig.colorbar(im, ax=ax, fraction=0.03, label="%")
plt.tight_layout()
plt.show()

# %% [markdown]
# Reanalysis models tend to produce more light-rain days than rain gauges record, so read these as
# relative patterns (which months and cities are wetter) rather than exact probabilities.
#
# ## The monthly summary file
#
# `idn_weather_monthly.csv` already aggregates every city-month (mean temperatures, total rain and
# rainy days), which is handy for joining with monthly business data such as sales or deliveries:

# %%
monthly = pd.read_csv(find("idn_weather_monthly.csv"), parse_dates=["month"])
monthly[monthly["city"] == "Jakarta"].tail(6).set_index(["city", "month"]).round(1)

# %% [markdown]
# ## Ideas for your own analysis
#
# - Use weather as features in a demand-forecasting model (beverages, umbrellas, electricity).
# - Relate rainfall to air pollution with the companion dataset
#   [Indonesia Air Quality: Hourly PM2.5, 31 Cities](https://www.kaggle.com/datasets/danielaijdkx/indonesia-air-quality-hourly-pm25).
# - Detect dry spells (consecutive days without rain) and their link to fires and haze.
#
# *Data: Open-Meteo Historical Weather API (CC BY 4.0), containing modified Copernicus Climate
# Change Service information. If this was useful, an upvote on the notebook and the dataset helps
# others find them.*
