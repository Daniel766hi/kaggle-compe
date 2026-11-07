"""Estimate pre-programme seasonality and seasonally adjust the calibration series.

Why: the SD model has no seasonal demand, so calibrating it to raw prices forces its parameters to
extreme values to "explain" Lebaran and year-end peaks. Instead, seasonal factors are estimated on
pre-MBG data (2007-2023) and removed from the 2024-2026 series before calibration (Section 3.4/3.5).

Model (per commodity), monthly, OLS:
    log(P_t / CMA_t) = sum_m a_m * [month = m] + b_pre * EidPre_t + b_post * EidPost_t + e_t
  CMA_t   : centred 2x12 moving average (removes trend and level, incl. the 2020 data splice)
  EidPre  : share of the 30 days BEFORE Idul Fitri that fall in month t
  EidPost : share of the 30 days AFTER Idul Fitri that fall in month t
  Sample  : 2007-07 to 2023-06, excluding Mar 2020 - Dec 2021 (COVID disruption) and outliers.
Calendar-month effects (a_m) capture fixed holidays (Christmas/New Year); the Eid terms capture the
moving Lebaran effect. Seasonal factor S_t = exp(fitted); adjusted price = P_t / S_t.

Outputs: data/seasonal_factors.csv, adds *_sa columns to data/historical_prices.csv,
         outputs*/seasonal_regression.csv and fig_seasonal_factors.png
"""
from datetime import date, timedelta

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import statsmodels.api as sm

from common import DATA_DIR, OUT_DIR, save_table

# Idul Fitri (1 Syawal) dates as observed in Indonesia. VERIFY against Kemenag decrees and cite.
EID = {2007: "2007-10-13", 2008: "2008-10-01", 2009: "2009-09-20", 2010: "2010-09-10",
       2011: "2011-08-31", 2012: "2012-08-19", 2013: "2013-08-08", 2014: "2014-07-28",
       2015: "2015-07-17", 2016: "2016-07-06", 2017: "2017-06-25", 2018: "2018-06-15",
       2019: "2019-06-05", 2020: "2020-05-24", 2021: "2021-05-13", 2022: "2022-05-02",
       2023: "2023-04-22", 2024: "2024-04-10", 2025: "2025-03-31", 2026: "2026-03-20",
       2027: "2027-03-10", 2028: "2028-02-27", 2029: "2029-02-14"}
EID = {y: date.fromisoformat(d) for y, d in EID.items()}


def eid_shares(period: pd.Period):
    start, end = period.start_time.date(), period.end_time.date()
    pre = post = 0
    for e in EID.values():
        for k in range(1, 31):
            if start <= e - timedelta(days=k) <= end:
                pre += 1
            if start <= e + timedelta(days=k - 1) <= end:
                post += 1
    return pre / 30, post / 30


long = pd.read_csv(DATA_DIR / "wfp_national_monthly_long.csv", index_col=0)
long.index = pd.PeriodIndex(long.index, freq="M")
long = long.reindex(pd.period_range(long.index.min(), long.index.max(), freq="M"))

# ---- outlier screen: > 40% away from centred 5-month rolling median -> missing
cleaned, removed = long.copy(), []
for c in long.columns:
    rm = long[c].rolling(5, center=True, min_periods=3).median()
    bad = (long[c] / rm - 1).abs() > 0.4
    for p in long.index[bad]:
        removed.append({"month": str(p), "series": c, "value": long.loc[p, c], "rolling_median": rm[p]})
    cleaned.loc[bad, c] = np.nan
pd.DataFrame(removed).to_csv(DATA_DIR / "outliers_removed.csv", index=False)
print("Outliers removed:", removed)

X_all = pd.DataFrame(index=cleaned.index)
X_all[["eid_pre", "eid_post"]] = [eid_shares(p) for p in cleaned.index]
for m in range(1, 13):
    X_all[f"m{m:02d}"] = (cleaned.index.month == m).astype(float)
future = pd.period_range(cleaned.index.max() + 1, "2029-12", freq="M")
Xf = pd.DataFrame(index=future)
Xf[["eid_pre", "eid_post"]] = [eid_shares(p) for p in future]
for m in range(1, 13):
    Xf[f"m{m:02d}"] = (future.month == m).astype(float)
X_full = pd.concat([X_all, Xf])

factors, reg_rows = pd.DataFrame(index=X_full.index), []
fig, axes = plt.subplots(1, 2, figsize=(12, 4))
for ax, c in zip(axes, ["egg", "chicken"]):
    s = cleaned[c].interpolate(limit=2)                       # only for the moving average
    cma = s.rolling(12, center=True).mean().rolling(2).mean().shift(-1)
    y = np.log(cleaned[c] / cma)
    sample = (y.index >= pd.Period("2007-07", "M")) & (y.index <= pd.Period("2023-06", "M")) \
        & ~((y.index >= pd.Period("2020-03", "M")) & (y.index <= pd.Period("2021-12", "M"))) & y.notna()
    res = sm.OLS(y[sample], X_all.loc[sample]).fit(cov_type="HAC", cov_kwds={"maxlags": 3})
    fitted = X_full @ res.params
    fitted = fitted - fitted.groupby(fitted.index.year).transform("mean")   # factors average 1 per year
    factors[c] = np.exp(fitted)
    for k in res.params.index:
        reg_rows.append({"series": c, "term": k, "coef": res.params[k], "se": res.bse[k], "p": res.pvalues[k]})
    reg_rows.append({"series": c, "term": "R2", "coef": res.rsquared, "se": np.nan, "p": np.nan})
    reg_rows.append({"series": c, "term": "n_obs", "coef": int(res.nobs), "se": np.nan, "p": np.nan})
    print(f"\n{c}: n={int(res.nobs)}, R2={res.rsquared:.3f}, Eid-pre={res.params['eid_pre']:+.3f} "
          f"(p={res.pvalues['eid_pre']:.3g}), Eid-post={res.params['eid_post']:+.3f} (p={res.pvalues['eid_post']:.3g}), "
          f"Dec={res.params['m12']:+.3f}")
    f = factors.loc["2024-01":"2026-12", c]
    ax.plot(f.index.to_timestamp(), f.values, marker="o", ms=3)
    ax.axhline(1, color="grey", lw=0.8)
    ax.set_title(f"Estimated seasonal factor: {c} (pre-programme data)")
fig.tight_layout()
fig.savefig(OUT_DIR / "fig_seasonal_factors.png", dpi=150)
save_table(pd.DataFrame(reg_rows).set_index(["series", "term"]), "seasonal_regression.csv")

factors.index = factors.index.astype(str)
factors.index.name = "month"
factors.to_csv(DATA_DIR / "seasonal_factors.csv")

h = pd.read_csv(DATA_DIR / "historical_prices.csv")
h["season_egg"] = h["month"].map(factors["egg"])
h["season_chicken"] = h["month"].map(factors["chicken"])
h["rel_egg_price_sa"] = h["rel_egg_price"] / h["season_egg"]
h["rel_chicken_price_sa"] = h["rel_chicken_price"] / h["season_chicken"]
h.to_csv(DATA_DIR / "historical_prices.csv", index=False)
print("\n", h[["month", "rel_egg_price", "rel_egg_price_sa", "rel_chicken_price", "rel_chicken_price_sa"]].round(3).to_string())
