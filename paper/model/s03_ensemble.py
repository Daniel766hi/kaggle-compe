"""Step 3: exploratory ensemble.

Latin Hypercube sample of N scenarios over UNCERTAINTIES. Every policy is run on the
SAME N scenarios (common random numbers), so policies can be compared with paired tests.

Usage:  python s03_ensemble.py [N]        (demo default N=400; use 5000+ for the paper)
"""
import sys
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd
from scipy.stats import qmc

from common import (CF_COLS, DEMO, DEMO_STAMP, OUT_DIR, POLICIES, UNCERTAINTIES, compute_outcomes,
                    counterfactual_params, n_jobs, run)

SEED = 20261107


def sample(n: int) -> pd.DataFrame:
    names = list(UNCERTAINTIES)
    lo = np.array([UNCERTAINTIES[k][0] for k in names])
    hi = np.array([UNCERTAINTIES[k][1] for k in names])
    u = qmc.LatinHypercube(d=len(names), seed=SEED).random(n)
    return pd.DataFrame(qmc.scale(u, lo, hi), columns=names)


def _cf_job(args):
    sid, scn = args
    return sid, run(counterfactual_params(POLICIES["P0 Baseline"](scn)), columns=CF_COLS)


def _job(args):
    sid, policy, scn, cf = args
    params = POLICIES[policy](scn)
    try:
        out = compute_outcomes(run(params), cf)
        out["ok"] = True
    except Exception as e:  # keep going; failures are reported
        out = {"ok": False, "error": str(e)[:200]}
    return {"scenario": sid, "policy": policy, **out}


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    X = sample(n)
    X.index.name = "scenario"
    t = time.time()
    with Pool(n_jobs()) as pool:
        # counterfactual (no programme) once per scenario; policy levers only act via the programme
        cfs = dict(pool.imap_unordered(_cf_job, [(i, X.loc[i].to_dict()) for i in X.index], chunksize=8))
        print(f"  counterfactuals done ({time.time() - t:.0f}s)", flush=True)
        jobs = [(i, p, X.loc[i].to_dict(), cfs[i]) for p in POLICIES for i in X.index]
        rows = []
        for k, r in enumerate(pool.imap_unordered(_job, jobs, chunksize=8), 1):
            rows.append(r)
            if k % 200 == 0:
                print(f"  {k}/{len(jobs)} runs  ({time.time() - t:.0f}s)", flush=True)
    res = pd.DataFrame(rows).merge(X.reset_index(), on="scenario")
    res = res.sort_values(["policy", "scenario"]).reset_index(drop=True)
    path = OUT_DIR / "ensemble_results.csv"
    res.to_csv(path, index=False)
    if DEMO_STAMP:
        (OUT_DIR / "ensemble_results.README.txt").write_text(DEMO_STAMP + "\n")
    print(f"{len(res)} runs in {time.time() - t:.0f}s; failed: {(~res['ok']).sum()}; saved {path}")


if __name__ == "__main__":
    main()
