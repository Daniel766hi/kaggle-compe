"""Validation B2: are the ensemble conclusions robust to the integration time step?

B1 (in s02_validation.py) checks one baseline run. This check reruns a random subset of the
ensemble scenarios at the model's TIME STEP and at half of it, for the main policies, and compares
spike classification and peak programme-attributable prices. Appends row B2 to
outputs/validation_tests.csv and writes outputs/time_step_robustness.csv.

Usage:  python check_time_step.py [n_scenarios]      (default 150; run after s03_ensemble.py)
"""
import sys
from multiprocessing import Pool

import pandas as pd

from common import (CF_COLS, DEMO_STAMP, OUT_DIR, POLICIES, compute_outcomes, counterfactual_params,
                    is_spike, model_time_step, n_jobs, run, save_table)
from s03_ensemble import sample

POLS = ["P0 Baseline", "P1 Phased roll-out", "P3 Forward contracts", "P5 Combined (P2+P3+P4)"]
N_ENSEMBLE = 5000          # same LHS design as the ensemble; the subset is drawn from it
AGREEMENT_PASS = 0.98      # pass if >= 98% of runs get the same spike classification


def _job(args):
    i, scn, dt = args
    cf = run(counterfactual_params(POLICIES["P0 Baseline"](scn)), columns=CF_COLS, time_step=dt)
    rows = []
    for p in POLS:
        o = compute_outcomes(run(POLICIES[p](scn), time_step=dt), cf)
        o.update(scenario=i, policy=p, dt=dt)
        rows.append(o)
    return rows


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 150
    dt = model_time_step()
    X = sample(N_ENSEMBLE).sample(n, random_state=1)
    jobs = [(i, X.loc[i].to_dict(), s) for i in X.index for s in (dt, dt / 2)]
    with Pool(n_jobs()) as pool:
        rows = [r for rs in pool.imap_unordered(_job, jobs, chunksize=2) for r in rs]
    d = pd.DataFrame(rows)
    d["spike"] = is_spike(d)
    w = d.pivot_table(index=["scenario", "policy"], columns="dt",
                      values=["spike", "peak_egg_price", "peak_chicken_price"])
    agree = float((w[("spike", dt)] == w[("spike", dt / 2)]).mean())
    summ = {"time_step": dt, "half_step": dt / 2, "scenarios": n, "policies": len(POLS),
            "spike_agreement": agree}
    for v in ["peak_egg_price", "peak_chicken_price"]:
        diff = (w[(v, dt)] - w[(v, dt / 2)]).abs()
        summ[f"{v}_median_abs_diff"] = float(diff.median())
        summ[f"{v}_p95_abs_diff"] = float(diff.quantile(0.95))
    by_pol = d.groupby(["policy", "dt"])["spike"].mean().unstack()
    by_pol.columns = [f"spike_prob_dt_{c:g}" for c in by_pol.columns]
    save_table(by_pol, "time_step_robustness.csv")
    save_table(pd.Series(summ, name="value").to_frame(), "time_step_robustness_summary.csv")

    # append B2 to the validation table written by s02_validation.py
    vpath = OUT_DIR / "validation_tests.csv"
    v = pd.read_csv(vpath, comment="#", index_col=0)
    label = f"B2 Ensemble robustness: TIME STEP {dt:g} vs {dt / 2:g} ({n} scenarios x {len(POLS)} policies)"
    v = v[~v.index.str.startswith("B2 ")]
    v.loc[label] = [f"same spike classification in >= {AGREEMENT_PASS:.0%} of runs",
                    f"{agree:.1%} agree; median |peak diff| {summ['peak_egg_price_median_abs_diff']:.4f}",
                    agree >= AGREEMENT_PASS]
    save_table(v, "validation_tests.csv")
    print(pd.Series(summ).to_string())
    print(by_pol.round(3).to_string())
    print("B2 pass:", agree >= AGREEMENT_PASS)


if __name__ == "__main__":
    main()
