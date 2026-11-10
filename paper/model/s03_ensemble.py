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
                    counterfactual_params, n_jobs, save_table)

SEED = 20261107


def sample(n: int) -> pd.DataFrame:
    names = list(UNCERTAINTIES)
    lo = np.array([UNCERTAINTIES[k][0] for k in names])
    hi = np.array([UNCERTAINTIES[k][1] for k in names])
    u = qmc.LatinHypercube(d=len(names), seed=SEED).random(n)
    return pd.DataFrame(qmc.scale(u, lo, hi), columns=names)


CHUNK = 500      # scenarios simulated together in one vectorized integration


def _chunk_job(args):
    """All policies plus the no-programme counterfactual for one block of scenarios."""
    import vector_sim as vs
    sub, policies, time_step = args
    scns = [sub.loc[i].to_dict() for i in sub.index]
    cfs = vs.frames(vs.run_batch([counterfactual_params(POLICIES["P0 Baseline"](s)) for s in scns],
                                 time_step, CF_COLS))
    rows = []
    for p in policies:
        dfs = vs.frames(vs.run_batch([POLICIES[p](s) for s in scns], time_step))
        for i, df, cf in zip(sub.index, dfs, cfs):
            ok = bool(np.isfinite(df.values).all() and np.isfinite(cf.values).all())
            out = compute_outcomes(df, cf) if ok else {}
            rows.append({"scenario": i, "policy": p, **out, "ok": ok})
    return rows


def simulate(X: pd.DataFrame, policies=None, time_step=None) -> list[dict]:
    """Outcomes for every scenario in X under each policy (vectorized, in parallel blocks)."""
    policies = list(policies or POLICIES)
    blocks = [(X.iloc[s:s + CHUNK], policies, time_step) for s in range(0, len(X), CHUNK)]
    with Pool(min(n_jobs(), len(blocks))) as pool:
        return [r for rs in pool.imap(_chunk_job, blocks) for r in rs]


def equivalence_check(X: pd.DataFrame, n: int = 3) -> float:
    """Vectorized runs must reproduce ordinary PySD runs (all policies + counterfactual)."""
    import vector_sim as vs
    scns = [X.iloc[i].to_dict() for i in range(n)]
    plist = [POLICIES[p](s) for s in scns for p in POLICIES]
    plist += [counterfactual_params(POLICIES["P0 Baseline"](s)) for s in scns]
    worst = vs.check_equivalence(plist, tol=1e-9)
    save_table(pd.Series({"runs_compared": len(plist), "max_relative_difference": worst,
                          "tolerance": 1e-9}, name="value").to_frame(), "vector_equivalence.csv")
    return worst


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    X = sample(n)
    X.index.name = "scenario"
    t = time.time()
    worst = equivalence_check(X)
    print(f"  vectorized vs PySD: max relative difference {worst:.2e} ({time.time() - t:.0f}s)", flush=True)
    rows = simulate(X)
    res = pd.DataFrame(rows).merge(X.reset_index(), on="scenario")
    res = res.sort_values(["policy", "scenario"]).reset_index(drop=True)
    path = OUT_DIR / "ensemble_results.csv"
    res.to_csv(path, index=False)
    if DEMO_STAMP:
        (OUT_DIR / "ensemble_results.README.txt").write_text(DEMO_STAMP + "\n")
    print(f"{len(res)} runs in {time.time() - t:.0f}s; failed: {(~res['ok']).sum()}; saved {path}")


if __name__ == "__main__":
    main()
