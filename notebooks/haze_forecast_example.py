# %% [markdown]
# # Tomorrow's haze: next-day PM2.5 forecast for 31 Indonesian cities
#
# This notebook uses the **[Indonesia Haze: Next-Day PM2.5 Forecast](https://www.kaggle.com/models/danielaijdkx/indonesia-haze-pm25-next-day)**
# model to forecast tomorrow's air quality from today's data in three daily-updated datasets:
# [air quality](https://www.kaggle.com/datasets/danielaijdkx/indonesia-air-quality-hourly-pm25),
# [weather](https://www.kaggle.com/datasets/danielaijdkx/indonesia-daily-weather-31-cities) and
# [fire hotspots](https://www.kaggle.com/datasets/danielaijdkx/indonesia-fire-hotspots-nasa-firms).
# Because the datasets update every day, re-running this notebook gives a fresh forecast.
#
# > PM2.5 here is the CAMS model estimate (via Open-Meteo), not a station measurement; see the model
# > card for how the model was tested.

# %%
import glob
import json
import os
import sys

import joblib
import matplotlib.pyplot as plt
import pandas as pd

INK, INK2, GRID, SURFACE, MUTED = "#0b0b0b", "#52514e", "#e6e5e0", "#fcfcfb", "#c3c2b7"
C = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
    "axes.titlesize": 13, "axes.titleweight": "bold", "axes.titlecolor": INK, "axes.titlelocation": "left",
    "font.size": 10.5, "figure.figsize": (11, 4.6), "figure.dpi": 110, "legend.frameon": False,
})


def find(name):
    """Locate a file from an attached dataset or model (/kaggle/input) or locally (DATA_ROOT)."""
    for root in ("/kaggle/input", os.environ.get("DATA_ROOT", "../input")):
        hits = glob.glob(f"{root}/**/{name}", recursive=True)
        if hits:
            return hits[0]
    raise FileNotFoundError(name)


# The model folder holds model.joblib, features.py and model_info.json.
model_dir = os.path.dirname(find("model.joblib"))
sys.path.insert(0, model_dir)
from features import build_features, predict_next_day  # noqa: E402

model = joblib.load(os.path.join(model_dir, "model.joblib"))
info = json.load(open(os.path.join(model_dir, "model_info.json")))
print("Model trained on", info["trained_on"][0], "to", info["trained_on"][1])

# %%
aq = pd.read_csv(find("idn_air_quality_daily.csv"), parse_dates=["date"])
cities = pd.read_csv(find("cities.csv"))
weather = pd.read_csv(find("idn_weather_daily.csv"), parse_dates=["date"])
hotspots = pd.read_parquet(find("hotspots.parquet"), columns=["acq_date", "latitude", "longitude"])

# Forecast from the last day all three datasets cover completely.
base_day = min(aq["date"].max(), weather["date"].max(), hotspots["acq_date"].max())
aq, weather = aq[aq["date"] <= base_day], weather[weather["date"] <= base_day]
hotspots = hotspots[hotspots["acq_date"] <= base_day]
# Only the last weeks are needed to build the inputs (lags and 7-day windows).
start = base_day - pd.Timedelta(days=45)
X = build_features(aq[aq["date"] >= start], weather[weather["date"] >= start - pd.Timedelta(days=30)],
                   hotspots[hotspots["acq_date"] >= start - pd.Timedelta(days=10)], cities)
today = X[X["date"] == X["date"].max()].dropna(subset=["pm25"]).copy()
today["pm25_tomorrow"] = predict_next_day(model, today)
today = today.merge(cities[["city", "province"]], on="city")
forecast_day = today["date"].max() + pd.Timedelta(days=1)
print(f"Forecast for {forecast_day:%A %d %B %Y}, from data up to {today['date'].max():%d %B}")

# %%
UNHEALTHY, WHO = info["unhealthy_threshold"], 15
f = today.sort_values("pm25_tomorrow")
fig, ax = plt.subplots(figsize=(11, 8))
colors = [C[7] if v >= UNHEALTHY else (C[3] if v >= WHO else C[2]) for v in f["pm25_tomorrow"]]
ax.barh(f["city"], f["pm25_tomorrow"], color=colors)
ax.scatter(f["pm25"], f["city"], color=INK, s=14, zorder=3, label="today")
ax.axvline(WHO, color=INK2, lw=1, ls="--")
ax.axvline(UNHEALTHY, color=C[7], lw=1, ls="--")
ax.set_title(f"Forecast daily PM2.5 for {forecast_day:%d %B %Y} (bars) and today (dots)")
ax.set_xlabel("PM2.5 (µg/m³); dashed: WHO guideline 15 and 'unhealthy' 55.5")
ax.grid(axis="y", visible=False)
ax.legend(loc="lower right")
plt.show()

unhealthy = f[f["pm25_tomorrow"] >= UNHEALTHY].sort_values("pm25_tomorrow", ascending=False)
print(f"Cities forecast above {UNHEALTHY} µg/m³ (unhealthy): {len(unhealthy)}")
unhealthy[["city", "province", "pm25", "fires_100km", "fires_300km", "rain_mm", "pm25_tomorrow"]].round(1)

# %% [markdown]
# ## How good is the forecast?
#
# Results on the held-out test period from the model card (the model was trained only on earlier
# data for this test). "Tomorrow = today" is the simple baseline to beat.

# %%
rows = []
for subset, block in info["test"]["metrics"].items():
    for method, s in block.items():
        if method != "rows":
            rows.append({"subset": subset, "method": method, "MAE": s["MAE"],
                         "alert precision": s["unhealthy_precision"], "alert recall": s["unhealthy_recall"]})
pd.DataFrame(rows)

# %% [markdown]
# The model is modestly more accurate than assuming tomorrow equals today and raises fewer false
# alarms, but it misses slightly more unhealthy days. The largest coefficients show what drives it:

# %%
pd.Series(info["coefficients"]).head(8).rename("coefficient (standardized)").to_frame()
