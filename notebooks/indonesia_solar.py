# %% [markdown]
# # Where does rooftop solar work best in Indonesia?
#
# This notebook explores **[Indonesia Solar Irradiance: 38 Provinces Daily](https://www.kaggle.com/datasets/danielaijdkx/indonesia-solar-irradiance-38-provinces-nasa)**,
# NASA POWER's daily sunlight, temperature and rain for every provincial capital since 2001.
#
# **Questions answered**
# 1. Which provincial capitals get the most sun, and how big is the gap?
# 2. When in the year is sunlight highest and lowest, city by city?
# 3. How much does rain season cut solar output?
# 4. What would a 3 kWp rooftop system produce, and how quickly could it pay back? (with stated assumptions)
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


daily = pd.read_csv(find("solar_daily.csv"), parse_dates=["date"])
cities = pd.read_csv(find("cities.csv")).sort_values("rank_ghi").reset_index(drop=True)  # 1 = sunniest
monthly = pd.read_csv(find("solar_monthly.csv"), parse_dates=["month"])
print(f"{daily['city'].nunique()} cities, {daily['date'].min():%d %b %Y} to {daily['date'].max():%d %b %Y}, {len(daily):,} days")

# %% [markdown]
# ## 1. The sunniest and least sunny capitals

# %%
c = cities.sort_values("ghi_kwh_m2_day")
fig, ax = plt.subplots(figsize=(11, 9))
ax.barh(c["city"] + " (" + c["province"] + ")", c["ghi_kwh_m2_day"], color="#eda100")
ax.set_xlim(c["ghi_kwh_m2_day"].min() * 0.9, c["ghi_kwh_m2_day"].max() * 1.03)
ax.set_xlabel("Average solar energy on a flat surface (kWh/m2/day)"); ax.grid(axis="y", visible=False)
ax.set_title("Average daily sunlight by provincial capital")
plt.show()
top, bottom = cities.iloc[0], cities.iloc[-1]
print(f"Sunniest: {top['city']} at {top['ghi_kwh_m2_day']:.2f} kWh/m2/day; least: {bottom['city']} at {bottom['ghi_kwh_m2_day']:.2f}. "
      f"The sunniest gets {100 * (top['ghi_kwh_m2_day'] / bottom['ghi_kwh_m2_day'] - 1):.0f}% more.")

# %% [markdown]
# ## 2. The solar year, city by city
#
# Average sunlight by calendar month, relative to each city's own yearly average (100 = average month).

# %%
m = daily.assign(m=daily["date"].dt.month).groupby(["city", "m"])["ghi_kwh_m2"].mean().unstack()
rel = (m.div(m.mean(axis=1), axis=0) * 100).loc[cities["city"]]
fig, ax = plt.subplots(figsize=(11, 10))
im = ax.imshow(rel, aspect="auto", cmap="RdYlBu_r", vmin=70, vmax=130)
ax.set_xticks(range(12), ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
ax.set_yticks(range(len(rel)), rel.index); ax.grid(False)
ax.set_title("Monthly sunlight vs the city's average (sorted from sunniest)")
fig.colorbar(im, ax=ax, shrink=0.6, label="% of average month")
plt.show()
south = cities[cities["latitude"] < -5]
north = cities[cities["latitude"] > 1]
print(f"Cities south of 5°S peak around month {south['best_month'].mode().iloc[0]}; north of 1°N around month "
      f"{north['best_month'].mode().iloc[0]}. Median seasonal swing: {cities['seasonal_swing_pct'].median():.0f}%.")

# %% [markdown]
# ## 3. Rain and sun
#
# Monthly rainfall against monthly sunlight, all cities: how much does a wet month cost?

# %%
mm = monthly.dropna(subset=["ghi_kwh_m2", "rain_mm"])
mm = mm[mm["days"] >= 28]
fig, ax = plt.subplots(figsize=(11, 5))
ax.scatter(mm["rain_mm"], mm["ghi_kwh_m2"] / mm["days"], s=4, alpha=0.15, color="#2a78d6")
slope, intercept = np.polyfit(mm["rain_mm"], mm["ghi_kwh_m2"] / mm["days"], 1)
xs = np.linspace(0, mm["rain_mm"].quantile(0.99), 50)
ax.plot(xs, intercept + slope * xs, color="#e34948", lw=2)
ax.set_xlim(0, mm["rain_mm"].quantile(0.99)); ax.set_xlabel("Rain in the month (mm)"); ax.set_ylabel("Sunlight (kWh/m2/day)")
ax.set_title("Wetter months, less sun")
plt.show()
print(f"Each extra 100 mm of monthly rain goes with {abs(slope) * 100:.2f} kWh/m2/day less sunlight on average "
      f"(correlation {np.corrcoef(mm['rain_mm'], mm['ghi_kwh_m2'] / mm['days'])[0, 1]:.2f}).")

# %% [markdown]
# ## 4. A 3 kWp rooftop system: output and a rough payback
#
# **Assumptions (change them to your case):** an 80% performance ratio (already in the dataset's PV estimate), a
# system cost of Rp 15 million per kWp installed, and every kWh replacing grid electricity at Rp 1,445/kWh. Real
# payback depends on the tariff, net-metering rules, roof angle, shading and financing.

# %%
SYSTEM_KWP, COST_PER_KWP, TARIFF = 3, 15_000_000, 1_445
c = cities.copy()
c["kwh_year"] = c["pv_kwh_per_kwp_year"] * SYSTEM_KWP
c["saving_rp_year"] = c["kwh_year"] * TARIFF
c["payback_years"] = SYSTEM_KWP * COST_PER_KWP / c["saving_rp_year"]
show = c.sort_values("payback_years")[["city", "province", "kwh_year", "saving_rp_year", "payback_years"]]
print(show.head(8).round(1).to_string(index=False))
print("...")
print(show.tail(5).round(1).to_string(index=False))
print(f"\nUnder these assumptions payback ranges from {show['payback_years'].min():.1f} to {show['payback_years'].max():.1f} years.")

# %% [markdown]
# ## Takeaways
#
# - Eastern and southern Indonesia (Nusa Tenggara, Bali, southern Sulawesi) get noticeably more sun than western
#   Sumatra and the Papuan highlands, as the ranking above shows.
# - The solar year depends on the hemisphere and the monsoon: the heatmap shows when each city peaks.
# - Rain explains much of the month-to-month variation, so a system sized on yearly averages under-delivers in the
#   wet season.
#
# **Limits**: NASA POWER values are satellite and model estimates for a ~55 x 70 km grid cell, not station data; the
# payback figures rest on the stated assumptions.
