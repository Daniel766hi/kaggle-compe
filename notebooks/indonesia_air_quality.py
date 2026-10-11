# %% [markdown]
# # Air pollution in 31 Indonesian cities: who breathes the worst air, and when?
#
# This notebook explores **[Indonesia Air Quality: Hourly PM2.5, 31 Cities](https://www.kaggle.com/datasets/danielaijdkx/indonesia-air-quality-hourly-pm25)**,
# which is refreshed every day.
#
# **Questions answered**
# 1. Which cities have the most polluted air, and how often do they exceed the WHO guideline?
# 2. When in the year is pollution worst, in big cities versus forest-fire regions?
# 3. What time of day is the air worst in Jakarta?
# 4. How extreme do haze episodes get?
# 5. Does rain or wind clean the air? (combining this dataset with the weather dataset)
#
# > **Important:** values are estimates from the CAMS global atmospheric model (about 40 km grid),
# > not ground-station measurements. They are consistent across cities and time, which makes them
# > good for comparisons and patterns, but they can differ from a local monitor's reading.

# %%
import glob
import os

import matplotlib.pyplot as plt
import matplotlib.transforms as mtransforms
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
WHO_24H = 15  # WHO 2021 guideline for the 24-hour mean of PM2.5, µg/m³


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
daily = pd.read_csv(find("idn_air_quality_daily.csv"), parse_dates=["date"])
cities = pd.read_csv(find("cities.csv"))
# Use complete days only (the newest day can be partial).
daily = daily[daily["hours"] >= 20].copy()
daily["month"] = daily["date"].dt.month
print(f"{daily['city'].nunique()} cities, {daily['date'].min():%Y-%m-%d} to {daily['date'].max():%Y-%m-%d}, "
      f"{len(daily):,} city-days")
daily.head()

# %% [markdown]
# ## 1. Which cities have the most polluted air?

# %%
by_city = (daily.groupby("city")
           .agg(pm25=("pm2_5_mean", "mean"), days_over_who=("exceeds_who_pm25", "mean"))
           .sort_values("pm25"))

fig, ax = plt.subplots(figsize=(11, 8))
colors = [C[1] if v > by_city["pm25"].quantile(0.8) else C[0] for v in by_city["pm25"]]
ax.barh(by_city.index, by_city["pm25"], color=colors, height=0.7)
ax.axvline(WHO_24H, color=INK2, lw=1, ls="--", zorder=1)
ax.text(WHO_24H, len(by_city) - 0.3, f" WHO 24-hour guideline ({WHO_24H} µg/m³)", color=INK2, fontsize=9, va="bottom")
for y, v in enumerate(by_city["pm25"]):
    ax.text(v + 0.8, y, f"{v:.0f}", va="center", fontsize=8.5, color=INK2,
            bbox=dict(boxstyle="square,pad=0.1", fc=SURFACE, ec="none"))
ax.set_title("Average PM2.5 by city (orange = top 20%)")
ax.set_xlabel("Mean daily PM2.5, µg/m³")
ax.grid(axis="y", visible=False)
plt.tight_layout()
plt.show()

table = by_city.sort_values("pm25", ascending=False).round({"pm25": 1})
table["days_over_who"] = (table["days_over_who"] * 100).round(0).astype(int).astype(str) + "%"
table.rename(columns={"pm25": "mean PM2.5 (µg/m³)", "days_over_who": "days above WHO guideline"})

# %% [markdown]
# **Java's big cities stand out.** Jakarta and Bandung have the highest averages and exceed the
# WHO guideline on almost every day, while cities in eastern Indonesia (Maluku and Papua) rarely do.
# Population density, traffic, industry and power plants are concentrated on Java.
#
# ## 2. When in the year is the air worst?
#
# Seasonal patterns differ a lot between cities, so the charts below show the **median** for each
# calendar month (medians keep a few extreme haze days from dominating).

# %%
month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
monthly = daily.groupby(["city", "month"])["pm2_5_mean"].median().unstack("city")

fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
for ax, group, title in [
    (axes[0], ["Jakarta", "Bandung", "Surabaya"], "Java's big cities: not all the same"),
    (axes[1], ["Palembang", "Pontianak", "Jambi"], "Fire-prone regions: Aug-Oct peak"),
]:
    for i, city in enumerate(group):
        ax.plot(monthly.index, monthly[city], color=C[i], marker="o", ms=4, label=city)
    ax.set_xticks(range(1, 13), month_names)
    ax.set_title(title)
    ax.set_ylabel("Median daily PM2.5, µg/m³")
    ax.set_ylim(bottom=0)
    ax.legend(loc="upper left")
plt.tight_layout()
plt.show()

# %% [markdown]
# - **Jakarta and Bandung** are worst in the **dry season** (about May to September), when there
#   is little rain to wash particles out of the air.
# - **Surabaya does the opposite**: its cleanest month is August and it peaks around December.
#   Why? Local wind patterns and the sea breeze are likely candidates; it is a good question to
#   investigate further.
# - Cities in **Sumatra and Kalimantan** peak in **August to October**, the peak season for land
#   and peat fires.
#
# ## 3. What time of day is the air worst in Jakarta?
#
# The hourly file has every hour in local time (`time_local`).

# %%
hourly = pd.read_parquet(find("idn_air_quality_hourly.parquet"), columns=["city", "time_local", "pm2_5"])
jkt = hourly[hourly["city"] == "Jakarta"]
by_hour = jkt.groupby(jkt["time_local"].dt.hour)["pm2_5"].mean()

fig, ax = plt.subplots()
ax.plot(by_hour.index, by_hour.values, color=C[0], marker="o", ms=4)
ax.set_xticks(range(0, 24, 2), [f"{h:02d}:00" for h in range(0, 24, 2)])
ax.set_ylim(bottom=0)
ax.set_title("Jakarta: average PM2.5 by hour of the day (local time, WIB)")
ax.set_ylabel("PM2.5, µg/m³")
plt.tight_layout()
plt.show()
print(f"Worst hour: {by_hour.idxmax():02d}:00 ({by_hour.max():.0f} µg/m³); "
      f"cleanest hour: {by_hour.idxmin():02d}:00 ({by_hour.min():.0f} µg/m³)")

# %% [markdown]
# Pollution is **highest at night and lowest around midday**. During the day the sun heats the
# ground and the lowest layer of the atmosphere mixes upward, diluting pollutants. At night that
# layer becomes shallow and traps emissions close to the ground. (Remember these are model values.)
#
# ## 4. Haze episodes: how extreme do they get?

# %%
worst = daily.nlargest(10, "pm2_5_mean")[["city", "province", "date", "pm2_5_mean", "pm2_5_max"]]
worst.round({"pm2_5_mean": 0, "pm2_5_max": 0})

# %%
hazy = daily.groupby("city")["pm2_5_mean"].max().idxmax()
series = daily[daily["city"] == hazy].set_index("date")["pm2_5_mean"]
fig, ax = plt.subplots()
ax.plot(series.index, series, color=C[1], lw=1.2)
ax.axhline(WHO_24H, color=INK2, lw=0.8, ls="--")
ax.set_title(f"{hazy}: daily mean PM2.5 (dashed = WHO guideline)")
ax.set_ylabel("PM2.5, µg/m³")
plt.tight_layout()
plt.show()

print(f"Days above 150 µg/m³ in {hazy}, by year:")
(series > 150).groupby(series.index.year).sum().rename("days").to_frame().T

# %% [markdown]
# Haze is not a constant problem: it hits hard in some years and almost disappears in others. Dry
# years, such as El Niño years, make peat fires more likely. A useful extension is to relate haze
# days to rainfall in the preceding months.
#
# ## 5. Does rain or wind clean the air?
#
# This section combines the air quality data with the companion dataset
# **[Indonesia Daily Weather: 31 Cities](https://www.kaggle.com/datasets/danielaijdkx/indonesia-daily-weather-31-cities)**.
# Add it to the notebook with *Add Input* to run this part; it uses the same city names and local dates.

# %%
try:
    weather = pd.read_csv(find("idn_weather_daily.csv"), parse_dates=["date"])
except FileNotFoundError:
    weather = None
    print("Weather dataset not attached: add it via 'Add Input' to run this section.")

if weather is not None:
    both = daily.merge(weather[["city", "date", "precipitation_sum", "wind_speed_10m_max"]], on=["city", "date"])
    jkt = both[both["city"] == "Jakarta"].copy()
    jkt["rain"] = pd.cut(jkt["precipitation_sum"], [-0.1, 0.1, 5, 20, 1000],
                         labels=["dry (0 mm)", "light (<5 mm)", "moderate (5-20 mm)", "heavy (>20 mm)"])
    rain_effect = jkt.groupby("rain", observed=True)["pm2_5_mean"].agg(["mean", "count"])

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(rain_effect.index.astype(str), rain_effect["mean"], color=C[0], width=0.6)
    for i, v in enumerate(rain_effect["mean"]):
        ax.text(i, v + 1, f"{v:.0f}", ha="center", color=INK2, fontsize=9.5)
    ax.set_title("Jakarta: mean PM2.5 by daily rainfall")
    ax.set_ylabel("PM2.5, µg/m³")
    ax.grid(axis="x", visible=False)
    plt.tight_layout()
    plt.show()
    print(rain_effect.round(1))
    print(f"Correlation of daily PM2.5 with max wind speed: {jkt['pm2_5_mean'].corr(jkt['wind_speed_10m_max']):.2f}")

# %% [markdown]
# **Heavy-rain days are clearly cleaner** than dry days, and windier days have lower PM2.5 (negative
# correlation): rain washes particles out of the air and wind disperses them. This is the same
# mechanism behind the dry-season peak in section 2.
#
# ## Ideas for your own analysis
#
# - Forecast tomorrow's PM2.5 for Jakarta from today's values plus weather (a good time-series project).
# - Cluster cities by their seasonal profile.
# - Count "unhealthy" hours using the `us_aqi` column (above 150 = unhealthy for everyone).
# - Map the cities with `cities.csv` (latitude/longitude included).
#
# *Data: Open-Meteo Air Quality API (CC BY 4.0), generated using Copernicus Atmosphere Monitoring
# Service information. If this was useful, an upvote on the notebook and the dataset helps others find them.*
