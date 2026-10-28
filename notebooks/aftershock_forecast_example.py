# %% [markdown]
# # After a strong quake: a 7-day aftershock forecast for Indonesia
#
# This notebook uses the **[Indonesia Aftershock Forecast](https://www.kaggle.com/models/danielaijdkx/indonesia-aftershock-forecast)**
# model with the daily-updated **[Indonesia Earthquakes](https://www.kaggle.com/datasets/danielaijdkx/indonesia-earthquakes-usgs-daily)**
# dataset to answer the question people ask after every strong earthquake: *how many aftershocks
# should we expect, and how likely is another strong one this week?*
#
# 1. Forecasts for the most recent M5.5+ quakes in the dataset.
# 2. How a forecast changes after the first 24 hours.
# 3. How good the forecasts were on quakes the model never saw.
#
# > This is a statistical forecast, not an official warning: follow BMKG for safety decisions.

# %%
import glob
import json
import os
import sys

import joblib
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
    "font.size": 10.5, "figure.figsize": (11, 4.6), "figure.dpi": 110, "legend.frameon": False,
})


def find(name):
    """Locate a file from an attached dataset or model (/kaggle/input) or locally (DATA_ROOT)."""
    for root in ("/kaggle/input", os.environ.get("DATA_ROOT", "../input")):
        hits = glob.glob(f"{root}/**/{name}", recursive=True)
        if hits:
            return hits[0]
    raise FileNotFoundError(name)


model_dir = os.path.dirname(find("model.joblib"))
sys.path.insert(0, model_dir)
from features import forecast  # noqa: E402

models = joblib.load(os.path.join(model_dir, "model.joblib"))
info = json.load(open(os.path.join(model_dir, "model_info.json")))
seq = pd.read_csv(find("aftershock_sequences.csv"), parse_dates=["time"])
print(f"Model trained on {info['data']['quakes']:,} quakes ({info['data']['first']} to {info['data']['last']}); "
      f"dataset has {len(seq):,} M5.5+ quakes up to {seq['time'].max():%d %B %Y}")

# %% [markdown]
# ## 1. The most recent strong quakes
#
# For each of the latest M5.5+ quakes nearest Indonesia: the forecast made right after it, and, where
# a week has passed, what actually happened.

# %%
latest = seq[seq["country"] == "Indonesia"].sort_values("time").tail(12).copy()
fc = forecast(models, latest)
table = pd.concat([latest[["time", "mag", "depth_km", "province"]], fc,
                   latest[["aftershocks_m45_7d", "aftershocks_m5_7d", "complete_7d"]]], axis=1)
table = table.rename(columns={"expected_m45": "forecast M4.5+", "p_any_m5": "chance of M5+",
                              "aftershocks_m45_7d": "actual M4.5+", "aftershocks_m5_7d": "actual M5+",
                              "complete_7d": "week over"})
table["chance of M5+"] = (table["chance of M5+"] * 100).round().astype(int).astype(str) + "%"
table.drop(columns="expected_m5").iloc[::-1].reset_index(drop=True)

# %% [markdown]
# ## 2. Updating after 24 hours
#
# A day after the quake, the number of aftershocks so far says a lot about how active the sequence
# is. Here is the same M7.0 shallow quake with 0, 3, 10 or 30 M4.5+ aftershocks in its first day.

# %%
quake = pd.DataFrame([{"latitude": -8.3, "longitude": 116.4, "depth_km": 15, "mag": 7.0,
                       "mag_type": "mww", "prior_m45_30d": 0}])
first = forecast(models, quake).iloc[0]
rows = [{"after": "right after the quake (days 1-7)", "expected M4.5+": first["expected_m45"],
         "chance of M5+": first["p_any_m5"]}]
for n in (0, 3, 10, 30):
    later = forecast(models, quake.assign(aftershocks_m45_1d=n), stage="after_24h").iloc[0]
    rows.append({"after": f"24 h, {n} aftershocks so far (days 2-7)", "expected M4.5+": later["expected_m45"],
                 "chance of M5+": later["p_any_m5"]})
upd = pd.DataFrame(rows)
fig, ax = plt.subplots(figsize=(11, 3.8))
ax.barh(upd["after"], upd["chance of M5+"] * 100, color=[C[0]] + [C[7]] * 4)
for y, p in enumerate(upd["chance of M5+"]):
    ax.text(p * 100 + 1, y, f"{p:.0%}", va="center")
ax.invert_yaxis()
ax.set_xlim(0, 105)
ax.set_xlabel("Chance of at least one M5+ aftershock (%)")
ax.set_title("A busy first day raises the forecast; a quiet one lowers it")
ax.grid(axis="y", visible=False)
plt.show()
upd.round(3)

# %% [markdown]
# ## 3. How good is it?
#
# From the model card: results on the held-out period, with models trained only on earlier quakes.
# The baseline is the classic *productivity law* (aftershock count grows with magnitude only).

# %%
rows = []
for key, e in info["stages"].items():
    for name, s in e["test"].items():
        rows.append({"forecast": key, "method": name + (" (chosen)" if name == e["chosen"] else ""),
                     "Poisson deviance": s["mean_poisson_deviance"], "MAE": s["MAE"],
                     "Brier (any M5+)": s.get("brier_any")})
pd.DataFrame(rows)

# %% [markdown]
# Calibration matters most for a probability: when the model said "X% chance of an M5+ aftershock",
# how often did one happen?

# %%
cal = pd.DataFrame(info["stages"]["at_mainshock/m5"]["test_calibration"])
fig, ax = plt.subplots(figsize=(6, 5))
ax.plot([0, 1], [0, 1], color=MUTED, lw=1, ls="--")
ax.scatter(cal["mean_forecast"], cal["observed"], s=cal["quakes"] * 2, color=C[0])
for r in cal.itertuples():
    ax.annotate(f"{r.quakes} quakes", (r.mean_forecast, r.observed), xytext=(8, -4), textcoords="offset points",
                fontsize=9)
ax.set_xlabel("Forecast chance")
ax.set_ylabel("Observed share")
ax.set_title("Calibration on the test period")
plt.show()
cal

# %% [markdown]
# ## Takeaways
#
# - Aftershock forecasts are probabilities, not predictions of a specific quake. The model gives the
#   expected number of aftershocks in the coming week and the chance of a strong (M5+) one.
# - Magnitude matters most, then depth: shallow quakes have far more aftershocks than deep ones.
# - The first day of a sequence is informative: updating after 24 hours sharpens the forecast.
#
# Data: U.S. Geological Survey ANSS Comprehensive Catalog (public domain).
