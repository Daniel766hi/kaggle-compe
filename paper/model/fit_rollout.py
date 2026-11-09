"""Fit the roll-out S-curve so that the model's OPERATIONAL kitchens match BGN's reported counts.

Fits Target kitchens, Rollout midpoint, Rollout steepness by least squares (absolute errors) on
data/mbg_rollout_observed.csv (the unverified launch row is excluded). Writes the values into the
.mdl and saves data/rollout_fit.csv. Run before s02_validation.py.
"""
import re

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from common import DATA_DIR, MODEL_FILE, run

obs = pd.read_csv(DATA_DIR / "mbg_rollout_observed.csv", parse_dates=["date"])
obs = obs[~obs["note"].fillna("").str.contains("VERIFY before use")]
obs["week"] = (obs["date"] - pd.Timestamp("2024-01-01")).dt.days / 7
names = ["Target kitchens", "Rollout midpoint", "Rollout steepness"]


def sim(x):
    r = run(dict(zip(names, x)), columns=["Operational kitchens"], use_calibrated=False,
            time_step=0.25)["Operational kitchens"]   # smooth kitchen dynamics: coarse step is enough for fitting
    return np.interp(obs["week"], r.index, r.values)


def loss(x):
    if x[0] <= 0 or x[2] <= 0.5:
        return 1e9
    return float(np.mean(((sim(x) - obs["sppg_operational"]) / 1000) ** 2))   # absolute error, thousands


r = minimize(loss, [27365, 96.9, 8.7], method="Nelder-Mead", options={"maxiter": 300, "xatol": 1e-2})
est = dict(zip(names, r.x))
fit = obs[["date", "week", "sppg_operational"]].copy()
fit["model"] = sim(r.x)
fit["rel_error"] = fit["model"] / fit["sppg_operational"] - 1
fit.to_csv(DATA_DIR / "rollout_fit.csv", index=False)
print(fit.round(3).to_string())
print({k: round(v, 2) for k, v in est.items()}, "RMSE = %.0f kitchens" % (1000 * np.sqrt(r.fun)))

s = MODEL_FILE.read_text()
for k, v in est.items():
    val = f"{v:.0f}" if k == "Target kitchens" else f"{v:.2f}"
    s = re.sub(rf"(\n{re.escape(k)}=\n\t)[^\n]+", rf"\g<1>{val}", s, count=1)
s = s.replace("From data: logistic fit to BGN operational SPPG counts Aug 2025 - Sep 2026 (data/mbg_rollout_observed.csv), K = 27,365 +/- 681.",
              "From data: fitted so that modelled operational SPPG match BGN counts (fit_rollout.py, data/rollout_fit.csv).")
s = s.replace("From data: logistic fit to BGN SPPG counts (midpoint approx. Nov 2025), +/- 0.7 weeks.",
              "From data: fitted to BGN SPPG counts via operational kitchens (fit_rollout.py).")
s = s.replace("From data: logistic fit to BGN SPPG counts, +/- 0.5 weeks. POLICY P1",
              "From data: fitted to BGN SPPG counts via operational kitchens (fit_rollout.py). POLICY P1")
MODEL_FILE.write_text(s)
