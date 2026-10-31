# %% [markdown]
# # How long does the hype last? Forecasting attention after a spike
#
# When a topic suddenly explodes on Indonesian Wikipedia, how many people will still be reading
# about it next week? This notebook uses the **[Wikipedia Attention Decay Forecast](https://www.kaggle.com/models/danielaijdkx/wikipedia-attention-decay-forecast)**
# model with the daily-updated **[What Indonesia Reads](https://www.kaggle.com/datasets/danielaijdkx/indonesian-wikipedia-daily-top-articles)**
# dataset.
#
# This is a **demand-shock forecasting** problem: like forecasting sales after a promotion or a news
# shock, the question is how fast demand returns to normal.
#
# 1. Forecasts for the latest spikes.
# 2. How good is it, compared with simple rules?
# 3. Which spikes last longer?

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

model = joblib.load(os.path.join(model_dir, "model.joblib"))
info = json.load(open(os.path.join(model_dir, "model_info.json")))
spikes = pd.read_csv(find("attention_spikes.csv"), parse_dates=["spike_date"])
print(f"Model: {info['chosen']}, trained on {info['data']['spikes']:,} spikes "
      f"({info['data']['first']} to {info['data']['last']}); dataset has {len(spikes):,} spikes "
      f"up to {spikes['spike_date'].max():%d %B %Y}")

# %% [markdown]
# ## 1. The latest spikes: forecast vs what happened

# %%
latest = spikes.sort_values("spike_date").tail(10)
fc = forecast(model, latest)
pd.concat([latest[["spike_date", "title", "spike_rank", "views_d0"]], fc[["forecast_next_7d"]],
           latest[["next_7d"]].rename(columns={"next_7d": "actual_next_7d"})], axis=1).iloc[::-1] \
    .reset_index(drop=True)

# %% [markdown]
# Daily detail for the biggest of them: the dots are what happened, the line is the forecast made
# on the spike day.

# %%
big = latest.nlargest(4, "views_d0")
fcb = forecast(model, big)
fig, axes = plt.subplots(1, len(big), figsize=(13, 3.6), sharey=False)
for ax, (i, r) in zip(np.atleast_1d(axes), big.iterrows()):
    days = list(range(-7, 15))
    actual = [r[f"views_m{-d}"] if d < 0 else (r["views_d0"] if d == 0 else r[f"views_p{d}"]) for d in days]
    ax.plot(days, actual, "o", ms=3.5, color=INK2, label="actual")
    ax.plot([0] + list(range(1, 8)), [r["views_d0"]] + [fcb.loc[i, f"forecast_p{h}"] for h in range(1, 8)],
            color=C[7], label="forecast")
    ax.set_title(r["title"][:28], fontsize=10.5)
    ax.set_xlabel("days from spike")
np.atleast_1d(axes)[0].legend()
np.atleast_1d(axes)[0].set_ylabel("daily views")
plt.show()

# %% [markdown]
# ## 2. How good is it?
#
# From the model card: the newest spikes were held out, and models were trained only on earlier
# ones. "Persistence" assumes views stay at the spike level; "typical decay" assumes every spike
# fades like the median spike.

# %%
pd.DataFrame({name: {"error on log scale": s["mae_log"], "7-day total: median error": s["next_7d_median_ape"],
                     "within 25%": s["next_7d_within_25pct"]} for name, s in info["test"].items()}).T

# %%
fig, ax = plt.subplots()
for (name, s), color in zip(info["test"].items(), [C[7], C[3], C[0], C[2]]):
    hs = sorted(int(h) for h in s["mae_log_by_horizon"])
    ax.plot(hs, [s["mae_log_by_horizon"][str(h)] for h in hs], marker="o", color=color, label=name)
ax.set_xlabel("Days after the spike")
ax.set_ylabel("Mean error (log scale)")
ax.set_title("Forecast error grows with the horizon; persistence is far off after day 1")
ax.legend()
plt.show()

# %% [markdown]
# ## 3. Which spikes last longer?
#
# The same spike size can fade in a day or stay for weeks. The model's forecast of the share kept
# after 3 days, by how the article was doing the day before the spike:

# %%
recent = spikes[spikes["spike_date"] >= spikes["spike_date"].quantile(0.8)].copy()
f = forecast(model, recent)
recent["forecast_kept_day3"] = f["forecast_p3"] / recent["views_d0"].clip(lower=1)
recent["actual_kept_day3"] = recent["views_p3"] / recent["views_d0"].clip(lower=1)
recent["day before"] = pd.cut(recent["views_m1"] / recent["views_d0"].clip(lower=1), [-0.01, 0.02, 0.2, 10],
                              labels=["quiet (<2%)", "some (2-20%)", "already rising (>20%)"])
recent.groupby("day before", observed=True)[["forecast_kept_day3", "actual_kept_day3"]].median().round(2)

# %% [markdown]
# ## Takeaways
#
# - Attention after a spike fades fast: typically about half is gone the next day.
# - A simple "typical decay" rule is a strong baseline; the model's gain comes from telling apart
#   one-day stories from developing ones (see the model card for the exact numbers).
# - The same method applies to demand after promotions or news shocks: forecast the decay from the
#   shape of the build-up and the size of the peak.
#
# Data: Wikimedia Foundation pageviews API (CC0).
