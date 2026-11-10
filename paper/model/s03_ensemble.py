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

from common import (CF_COLS, model_time_step, DEMO, DEMO_STAMP, OUT_DIR, POLICIES, UNCERTAINTIES, compute_outcomes,
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
    """Runs are checkpointed in outputs/_ensemble_parts/ so that an interrupted run resumes where it stopped."""
    import pickle
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    X = sample(n)
    X.index.name = "scenario"
    parts = OUT_DIR / "_ensemble_parts"
    parts.mkdir(parents=True, exist_ok=True)
    tag = f"n{n}_dt{model_time_step():g}"
    for old in parts.glob("*"):          # parts from a different ensemble size or time step are stale
        if tag not in old.name:
            old.unlink()
    t = time.time()
    with Pool(n_jobs()) as pool:
        # counterfactual (no programme) once per scenario; policy levers only act via the programme
        cf_file = parts / f"counterfactuals_{tag}.pkl"
        if cf_file.exists():
            cfs = pickle.loads(cf_file.read_bytes())
            print(f"  counterfactuals loaded from checkpoint", flush=True)
        else:
            cfs = dict(pool.imap_unordered(_cf_job, [(i, X.loc[i].to_dict()) for i in X.index], chunksize=8))
            cf_file.write_bytes(pickle.dumps(cfs))
            print(f"  counterfactuals done ({time.time() - t:.0f}s)", flush=True)
        rows = [r for f in sorted(parts.glob(f"part_{tag}_*.pkl")) for r in pickle.loads(f.read_bytes())]
        done = {(r["scenario"], r["policy"]) for r in rows}
        jobs = [(i, p, X.loc[i].to_dict(), cfs[i]) for p in POLICIES for i in X.index if (i, p) not in done]
        total = len(done) + len(jobs)
        if done:
            print(f"  resuming: {len(done)} runs loaded from checkpoints, {len(jobs)} to go", flush=True)
        buf, k0 = [], len(list(parts.glob(f"part_{tag}_*.pkl")))
        for k, r in enumerate(pool.imap_unordered(_job, jobs, chunksize=8), 1):
            rows.append(r)
            buf.append(r)
            if len(buf) >= 1000 or k == len(jobs):
                (parts / f"part_{tag}_{k0:04d}.pkl").write_bytes(pickle.dumps(buf))
                buf, k0 = [], k0 + 1
            if k % 200 == 0:
                print(f"  {len(done) + k}/{total} runs  ({time.time() - t:.0f}s)", flush=True)
    res = pd.DataFrame(rows).merge(X.reset_index(), on="scenario")
    res = res.sort_values(["policy", "scenario"]).reset_index(drop=True)
    path = OUT_DIR / "ensemble_results.csv"
    res.to_csv(path, index=False)
    if DEMO_STAMP:
        (OUT_DIR / "ensemble_results.README.txt").write_text(DEMO_STAMP + "\n")
    print(f"{len(res)} runs in {time.time() - t:.0f}s; failed: {(~res['ok']).sum()}; saved {path}")


if __name__ == "__main__":
    main()
