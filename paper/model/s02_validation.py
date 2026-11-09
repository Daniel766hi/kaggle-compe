"""Step 2: model validation (Barlas 1996; Sterman 2000).

A. Extreme-condition tests  - model must behave plausibly under extreme inputs.
B. Integration-error test   - results must not depend on TIME STEP.
C. Behaviour reproduction   - fit to historical prices (needs data/historical_prices.csv).
D. Parameter-recovery test  - calibration must recover known parameters from synthetic data
                              (checks the calibration procedure itself before using real data).
"""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.optimize import minimize

from common import DATA_DIR, OUT_DIR, model_time_step, run, save_table, stamp

STOCK_COLS = ["Laying hens", "Pullets", "Operational kitchens", "Suspended kitchens"]
COLS = ["Relative egg price", "Relative chicken price", "Laying hens", "Pullets",
        "Operational kitchens", "Suspended kitchens", "Household egg consumption ratio",
        "Household chicken consumption ratio", "Egg production", "Relative egg coverage",
        "Programme coverage"]


def sane(df):
    finite = np.isfinite(df.values).all()
    nonneg = (df[STOCK_COLS] >= -1e-6).all().all()
    return bool(finite and nonneg)


# ------------------------------------------------------------------ A. extreme conditions
tests = []

df = run({"Programme start time": 10_000}, columns=COLS)
dev = float(np.abs(df["Relative egg price"] - 1).max())
tests.append(("A1 No programme -> system stays in equilibrium",
              "max |relative egg price - 1| < 1e-6", f"{dev:.2e}", sane(df) and dev < 1e-6))

df = run({"Egg per beneficiary": 1.0, "Chicken per beneficiary": 1.5}, columns=COLS)
pk = df["Relative egg price"].max()
hh = df["Household egg consumption ratio"].min()
tests.append(("A2 10x programme demand -> price up, household consumption down",
              "peak price > 1.2 and household ratio < 0.9; finite, no negative stocks",
              f"peak={pk:.2f}, hh_min={hh:.2f}", sane(df) and pk > 1.2 and hh < 0.9))

df = run({"Outbreak loss fraction": 1.0}, columns=COLS)
hens_min = df["Laying hens"].min()
tests.append(("A3 Outbreak kills 100% of hens -> production collapses, price spikes, no negatives",
              "min hens < 10% of initial; 1.5 < peak price <= ceiling; no negative stocks",
              f"min hens={hens_min:,.0f}, peak={df['Relative egg price'].max():.2f}",
              sane(df) and hens_min < 0.10 * df["Laying hens"].iloc[0]
              and 1.5 < df["Relative egg price"].max() <= 3.0 + 1e-6))

base = run(columns=COLS)
df = run({"Hatchery capacity factor": 1.0}, columns=COLS)
tests.append(("A4 No hatchery expansion possible -> higher prices than baseline",
              "mean price (weeks 100-312) above baseline run",
              f"{df.loc[100:, 'Relative egg price'].mean():.3f} vs {base.loc[100:, 'Relative egg price'].mean():.3f}",
              sane(df) and df.loc[100:, "Relative egg price"].mean() > base.loc[100:, "Relative egg price"].mean()))

df = run({"Feed shock magnitude": 1.0}, columns=COLS)
tests.append(("A5 Feed price doubles -> egg price rises during shock",
              "price at week 140 above baseline run",
              f"{df.loc[140, 'Relative egg price']:.3f} vs {base.loc[140, 'Relative egg price']:.3f}",
              sane(df) and df.loc[140, "Relative egg price"] > base.loc[140, "Relative egg price"]))

df = run({"Rollout steepness": 0.5}, columns=COLS)
tests.append(("A6 Near-instant roll-out (steepness 0.5 wk) -> more suspensions than baseline (scaling strain)",
              "peak suspended kitchens above baseline run",
              f"{df['Suspended kitchens'].max():,.0f} vs {base['Suspended kitchens'].max():,.0f}",
              sane(df) and df["Suspended kitchens"].max() > base["Suspended kitchens"].max()))

# ------------------------------------------------------------------ B. integration error
DT = model_time_step()
a = run(columns=COLS)
b = run(time_step=DT / 2, columns=COLS)
key = ["Relative egg price", "Relative chicken price", "Laying hens", "Programme coverage"]
rng_ = (a[key].max() - a[key].min()).replace(0, 1)
rel = float(((a[key] - b[key]).abs().max() / rng_).max())
tests.append((f"B1 Integration error: TIME STEP {DT:g} vs {DT / 2:g}",
              "max |difference| < 1% of each variable's range",
              f"{rel:.4%}", rel < 0.01))

res = pd.DataFrame(tests, columns=["Test", "Pass criterion", "Observed", "Pass"]).set_index("Test")
save_table(res, "validation_tests.csv")
print(res.to_string())


# ------------------------------------------------------------------ C/D. calibration tools
def theil(sim, obs):
    """MSE decomposition into bias (Um), unequal variance (Us), unequal covariance (Uc)."""
    sim, obs = np.asarray(sim, float), np.asarray(obs, float)
    mse = np.mean((sim - obs) ** 2)
    if mse == 0:
        return dict(MSE=0, Um=0, Us=0, Uc=0)
    r = np.corrcoef(sim, obs)[0, 1]
    um = (sim.mean() - obs.mean()) ** 2 / mse
    us = (sim.std() - obs.std()) ** 2 / mse
    uc = 2 * (1 - r) * sim.std() * obs.std() / mse
    return dict(MSE=mse, Um=um, Us=us, Uc=uc)


def fit_stats(sim, obs):
    sim, obs = np.asarray(sim, float), np.asarray(obs, float)
    mape = float(np.mean(np.abs((sim - obs) / obs)))
    r2 = float(np.corrcoef(sim, obs)[0, 1] ** 2)
    return {"MAPE": mape, "R2": r2, **theil(sim, obs)}


CAL_PARAMS = {"Price expectation delay": (2, 20), "Investment sensitivity": (0.2, 4),
              "Price sensitivity to coverage": (0.2, 3)}
# parameters estimated from the real price data (joint egg + chicken fit)
# Not estimated (shown not identifiable by the 29 monthly observations): Price expectation delay
# (moved between both bounds) and Price sensitivity to coverage (SSE profile almost flat from 1 to 10;
# see identifiability_profile.csv). Both are fixed in the .mdl and explored in the ensemble.
REAL_CAL_PARAMS = {"Investment sensitivity": (0.2, 6), "Broiler investment sensitivity": (0.0, 4)}
PROFILE = {"Price sensitivity to coverage": [0.5, 1, 2, 3, 5, 10], "Price expectation delay": [2, 4, 8, 16, 30]}


def calibrate(targets: dict, params=None, z0=None, maxiter=400):
    """Least squares over one or more series. targets = {model column: observed Series (index=week)}."""
    params = params or CAL_PARAMS
    names = list(params)
    lo = np.array([params[n][0] for n in names])
    hi = np.array([params[n][1] for n in names])
    cols = list(targets)

    def loss(z):
        x = lo + (hi - lo) / (1 + np.exp(-z))          # keep inside bounds
        sim = run(dict(zip(names, x)), columns=cols, use_calibrated=False)
        return float(sum(np.mean((sim[c].reindex(o.index) - o) ** 2) for c, o in targets.items()))

    z0 = np.zeros(len(names)) if z0 is None else np.asarray(z0, float)
    r = minimize(loss, z0, method="Nelder-Mead", options={"maxiter": maxiter, "xatol": 1e-3, "fatol": 1e-10})
    x = lo + (hi - lo) / (1 + np.exp(-r.x))
    return dict(zip(names, x)), r.fun


def _start(args):
    targets, z0 = args
    return calibrate(targets, REAL_CAL_PARAMS, z0=z0)


# D. parameter-recovery test on synthetic data (method check, not a result)
true = {"Price expectation delay": 12.0, "Investment sensitivity": 2.2, "Price sensitivity to coverage": 1.4}
rng = np.random.default_rng(1)
synth = run(true, columns=["Relative egg price"], use_calibrated=False)["Relative egg price"]
synth = synth.loc[52:200] + rng.normal(0, 0.003, len(synth.loc[52:200]))
est, mse = calibrate({"Relative egg price": synth})
rec = pd.DataFrame({"true": true, "estimated": est})
rec["abs_error_%"] = 100 * (rec["estimated"] - rec["true"]).abs() / rec["true"]
save_table(rec, "parameter_recovery_test.csv")
print("\nD. Parameter-recovery test (synthetic data, checks the calibration method):")
print(rec.round(3).to_string())

# C. calibration + behaviour reproduction on real data (seasonally adjusted, eggs and chicken jointly)
hist = DATA_DIR / "historical_prices.csv"
if hist.exists():
    from multiprocessing import Pool
    h = pd.read_csv(hist).set_index("week")
    sa = "rel_egg_price_sa" in h.columns
    eg, ck = ("rel_egg_price_sa", "rel_chicken_price_sa") if sa else ("rel_egg_price", "rel_chicken_price")
    targets = {"Relative egg price": h[eg], "Relative chicken price": h[ck]}
    starts = [np.zeros(len(REAL_CAL_PARAMS))] + [np.random.default_rng(k).normal(0, 1.2, len(REAL_CAL_PARAMS))
                                                 for k in range(3)]
    with Pool(4) as pool:
        fits = pool.map(_start, [(targets, z) for z in starts])
    fits = sorted(fits, key=lambda f: f[1])
    est, best = fits[0]
    starts_tbl = pd.DataFrame([{**f[0], "SSE": f[1]} for f in fits])
    save_table(starts_tbl, "calibration_multistart.csv")
    cal = pd.DataFrame({"estimate": est,
                        "lower_bound": {k: v[0] for k, v in REAL_CAL_PARAMS.items()},
                        "upper_bound": {k: v[1] for k, v in REAL_CAL_PARAMS.items()}})
    width = cal["upper_bound"] - cal["lower_bound"]
    cal["at_bound"] = ((cal["estimate"] - cal["lower_bound"]) < 0.02 * width) | \
                      ((cal["upper_bound"] - cal["estimate"]) < 0.02 * width)
    cal["spread_across_starts"] = starts_tbl[list(REAL_CAL_PARAMS)].std().reindex(cal.index)
    cal.to_csv(DATA_DIR / "calibrated_parameters.csv")
    save_table(cal, "calibrated_parameters.csv")

    sim = run(est, columns=list(targets), use_calibrated=False).reindex(h.index)
    rows = {}
    for lab, c, o in [("egg (seasonally adjusted)", "Relative egg price", h[eg]),
                      ("chicken (seasonally adjusted)", "Relative chicken price", h[ck])]:
        rows[lab] = fit_stats(sim[c], o)
    if sa:  # re-apply seasonal factors to compare with raw observations
        rows["egg (raw, sim x seasonal factor)"] = fit_stats(sim["Relative egg price"] * h["season_egg"], h["rel_egg_price"])
        rows["chicken (raw, sim x seasonal factor)"] = fit_stats(sim["Relative chicken price"] * h["season_chicken"],
                                                                 h["rel_chicken_price"])
    stats = pd.DataFrame(rows).T
    save_table(stats, "behaviour_reproduction.csv")

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.2))
    for ax, c, o, t in [(axes[0], "Relative egg price", h[eg], "Eggs"),
                        (axes[1], "Relative chicken price", h[ck], "Chicken")]:
        full = run(est, columns=[c], use_calibrated=False)[c]
        ax.plot(o.index, o, "k.", ms=5, label="Observed, seasonally adjusted (WFP/HDX)")
        ax.plot(full.index, full, label="Simulated (calibrated)")
        ax.axvline(52, color="grey", ls=":", lw=0.8)
        ax.set_xlim(0, 160); ax.set_title(t); ax.set_xlabel("Week (0 = Jan 2024)")
        ax.set_ylabel("Price relative to 2024")
    axes[0].legend(fontsize=8)
    stamp(fig); fig.tight_layout(); fig.savefig(OUT_DIR / "fig_behaviour_reproduction.png", dpi=150)
    prof = []
    for k, vals in PROFILE.items():
        for val in vals:
            r_ = run({**est, k: val}, columns=list(targets), use_calibrated=False).reindex(h.index)
            sse = sum(np.mean((r_[c] - o) ** 2) for c, o in targets.items())
            prof.append({"parameter": k, "value": val, "SSE": sse})
    prof = pd.DataFrame(prof)
    save_table(prof.set_index(["parameter", "value"]), "identifiability_profile.csv")
    print("\nIdentifiability profile (SSE with calibrated parameters held fixed):\n", prof.round(6).to_string(index=False))
    print("\nC. Calibration (best of", len(fits), "starts):\n", cal.round(4).to_string())
    print("\nBehaviour reproduction:\n", stats.round(4).to_string())
else:
    print(f"\nC. Behaviour reproduction skipped: add {hist.name} (see data/README.md).")

print("\nAll extreme-condition and integration tests passed:", bool(res["Pass"].all()))
