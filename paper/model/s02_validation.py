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

from common import DATA_DIR, OUT_DIR, run, save_table, stamp

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

df = run({"Rollout duration": 1}, columns=COLS)
tests.append(("A6 Instant roll-out (1 week) -> more suspensions than baseline (loop R1)",
              "peak suspended kitchens above baseline run",
              f"{df['Suspended kitchens'].max():,.0f} vs {base['Suspended kitchens'].max():,.0f}",
              sane(df) and df["Suspended kitchens"].max() > base["Suspended kitchens"].max()))

# ------------------------------------------------------------------ B. integration error
a = run(columns=COLS)
b = run(time_step=0.0625, columns=COLS)
key = ["Relative egg price", "Relative chicken price", "Laying hens", "Programme coverage"]
rng_ = (a[key].max() - a[key].min()).replace(0, 1)
rel = float(((a[key] - b[key]).abs().max() / rng_).max())
tests.append(("B1 Integration error: TIME STEP 0.125 vs 0.0625",
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


def calibrate(obs: pd.Series, column="Relative egg price", x0=None):
    names = list(CAL_PARAMS)
    lo = np.array([CAL_PARAMS[n][0] for n in names])
    hi = np.array([CAL_PARAMS[n][1] for n in names])

    def loss(z):
        x = lo + (hi - lo) / (1 + np.exp(-z))          # keep inside bounds
        sim = run(dict(zip(names, x)), columns=[column])[column].reindex(obs.index)
        return float(np.mean((sim - obs) ** 2))

    z0 = np.zeros(len(names)) if x0 is None else np.log((np.array(x0) - lo) / (hi - np.array(x0)))
    r = minimize(loss, z0, method="Nelder-Mead", options={"maxiter": 250, "xatol": 1e-3, "fatol": 1e-9})
    x = lo + (hi - lo) / (1 + np.exp(-r.x))
    return dict(zip(names, x)), r.fun


# D. parameter-recovery test on synthetic data (method check, not a result)
true = {"Price expectation delay": 12.0, "Investment sensitivity": 2.2, "Price sensitivity to coverage": 1.4}
rng = np.random.default_rng(1)
synth = run(true, columns=["Relative egg price"])["Relative egg price"]
synth = synth.loc[52:200] + rng.normal(0, 0.003, len(synth.loc[52:200]))
est, mse = calibrate(synth)
rec = pd.DataFrame({"true": true, "estimated": est})
rec["abs_error_%"] = 100 * (rec["estimated"] - rec["true"]).abs() / rec["true"]
save_table(rec, "parameter_recovery_test.csv")
print("\nD. Parameter-recovery test (synthetic data, checks the calibration method):")
print(rec.round(3).to_string())

# C. behaviour reproduction with real data, if the user has supplied it
hist = DATA_DIR / "historical_prices.csv"
if hist.exists():
    h = pd.read_csv(hist).set_index("week")
    est, _ = calibrate(h["rel_egg_price"])
    sim = run(est, columns=["Relative egg price"])["Relative egg price"].reindex(h.index)
    stats = pd.DataFrame([fit_stats(sim, h["rel_egg_price"])], index=["egg"])
    save_table(stats, "behaviour_reproduction.csv")
    save_table(pd.Series(est, name="calibrated").to_frame(), "calibrated_parameters.csv")
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(h.index, h["rel_egg_price"], "k.", ms=3, label="Historical (Panel Harga Pangan)")
    ax.plot(sim.index, sim, label="Simulated")
    ax.set_xlabel("Week (0 = Jan 2024)"); ax.set_ylabel("Relative egg price"); ax.legend()
    stamp(fig); fig.tight_layout(); fig.savefig(OUT_DIR / "fig_behaviour_reproduction.png", dpi=150)
    print("\nC. Behaviour reproduction:\n", stats.round(4).to_string())
else:
    print(f"\nC. Behaviour reproduction skipped: add {hist.name} (see data/README.md).")

print("\nAll extreme-condition and integration tests passed:", bool(res["Pass"].all()))
