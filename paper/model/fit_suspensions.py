"""Fit kitchen-suspension parameters to BGN reports.

Targets (data/mbg_rollout_observed.csv notes and sources below):
  * 8,182 SPPG had been suspended at some point, and 2,213 were still inactive, by about 31 May 2026
    (Jawapos / detik, citing BGN evaluation).
Fitted: Base suspension fraction, Reinstatement time. Strain sensitivity stays an uncertainty.
Note: real suspensions came largely in an enforcement wave (e.g. 1,256 SPPG in eastern Indonesia from
1 April 2026 for missing hygiene certificates), which a constant hazard only approximates.
"""
import re

import numpy as np
from scipy.optimize import minimize

from common import MODEL_FILE, run

WEEK = (np.datetime64("2026-05-31") - np.datetime64("2024-01-01")).astype(int) / 7
CUM_TARGET, STOCK_TARGET = 8182, 2213
names = ["Base suspension fraction", "Reinstatement time"]


def sim(x):
    r = run(dict(zip(names, x)), columns=["Suspension rate", "Suspended kitchens"], use_calibrated=False)
    cum = r.loc[:WEEK, "Suspension rate"].sum()          # weekly save points, rate per week
    stock = float(np.interp(WEEK, r.index, r["Suspended kitchens"]))
    return cum, stock


def loss(x):
    if not (0 < x[0] < 0.05 and 0.5 < x[1] < 60):
        return 1e9
    cum, stock = sim(x)
    return (cum / CUM_TARGET - 1) ** 2 + (stock / STOCK_TARGET - 1) ** 2


r = minimize(loss, [0.004, 10], method="Nelder-Mead", options={"xatol": 1e-5, "fatol": 1e-8, "maxiter": 300})
cum, stock = sim(r.x)
print(f"Base suspension fraction={r.x[0]:.5f}/week, Reinstatement time={r.x[1]:.1f} weeks -> "
      f"cumulative {cum:,.0f} (target {CUM_TARGET:,}), suspended {stock:,.0f} (target {STOCK_TARGET:,})")
s = MODEL_FILE.read_text()
s = re.sub(r"(\nBase suspension fraction=\n\t)[^\n]+", rf"\g<1>{r.x[0]:.5f}", s, count=1)
s = re.sub(r"(\nReinstatement time=\n\t)[^\n]+", rf"\g<1>{r.x[1]:.2f}", s, count=1)
s = s.replace("UNCERTAINTY: weekly suspension probability at sustainable scaling.",
              "From data: fitted to BGN reports of 8,182 SPPG ever suspended and 2,213 inactive by end May 2026 (fit_suspensions.py). UNCERTAINTY.")
s = s.replace("PLACEHOLDER: time for a suspended kitchen to reopen.",
              "From data: fitted with Base suspension fraction (fit_suspensions.py).")
MODEL_FILE.write_text(s)
