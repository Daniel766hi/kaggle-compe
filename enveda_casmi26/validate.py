"""Honest local validation for the library search (class-1 style molecules).

    python -m enveda_casmi26.validate TRAIN.parquet WORKDIR [--build]

Queries: every `enveda-np-examples` structure plus 500 sampled `enveda-180` structures that also
have spectra in some other library. All spectra of the query structures *from those two
timsTOF libraries* are removed from the library; their spectra from other libraries stay, which
is the situation of a class-1 test molecule. A query "molecule" is one structure's held-out
spectra. The score is MRR@25 on InChIKey-14 (the metric also compares InChIKey-14 after
tautomer canonicalisation, which this approximation skips).
"""

import argparse
import os
import time

import numpy as np
import pandas as pd

from .library import Library, build
from .search import Searcher

SEED = 0


def holdout_keys(train_path):
    t = pd.read_parquet(train_path, columns=["inchikey14", "ingest_lib"])
    npx = set(t.inchikey14[t.ingest_lib == "enveda-np-examples"])
    e180 = t.ingest_lib == "enveda-180"
    shared = sorted(set(t.inchikey14[e180]) & set(t.inchikey14[~e180]) - npx)
    rng = np.random.default_rng(SEED)
    e180_keys = set(rng.choice(shared, size=min(500, len(shared)), replace=False))
    return npx, e180_keys


def mrr(ranked_keys, truth):
    for r, k in enumerate(ranked_keys[:25], 1):
        if k == truth:
            return 1.0 / r
    return 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("train")
    ap.add_argument("work")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--tol-ppm", type=float, default=10.0)
    ap.add_argument("--prior", type=float, default=0.02)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    lib_path = os.path.join(a.work, "lib_val")
    npx, e180 = holdout_keys(a.train)
    held = npx | e180
    hold_libs = {"enveda-np-examples", "enveda-180"}
    if a.build or not os.path.exists(lib_path + ".npz"):
        lib = build(a.train, exclude=lambda m: m.inchikey14.isin(held).to_numpy()
                    & m.ingest_lib.isin(hold_libs).to_numpy())
        lib.save(lib_path)
    lib = Library.load(lib_path)

    cols = ["inchikey14", "ingest_lib", "adduct", "ionization_mode", "precursor_mz",
            "ms2_mzs", "ms2_normalized_intensities"]
    q = pd.read_parquet(a.train, columns=cols, filters=[("ingest_lib", "in", list(hold_libs)),
                                                         ("inchikey14", "in", sorted(held))])
    # keep the test's adducts only, and at most 16 spectra per molecule like the test
    test_adducts = ["[M+H]+", "[M+NH4]+", "[M-H2O+H]+", "[M-2H2O+H]+", "[M+Na]+", "[M+K]+",
                    "[M-H]-", "[M-H2O-H]-", "[M+CH2O2-H]-", "[M+Cl]-"]
    q = q[q.adduct.isin(test_adducts)]
    q = q.groupby("inchikey14").head(16)
    s = Searcher(lib, tol_ppm=a.tol_ppm, prior=a.prior)
    rows, t0 = [], time.time()
    groups = list(q.groupby("inchikey14"))
    if a.limit:
        groups = groups[: a.limit]
    for i, (key, g) in enumerate(groups):
        ranked = s.rank(g)
        keys = [lib.structures.inchikey14.iat[sid] for sid, _ in ranked]
        rows.append(dict(key=key, set="np-examples" if key in npx else "enveda-180",
                         rr=mrr(keys, key), n_cands=len(lib.candidates(s.query_mass(g), a.tol_ppm)),
                         in_cands=key in set(lib.structures.inchikey14.iloc[
                             lib.candidates(s.query_mass(g), a.tol_ppm)])))
        if i % 100 == 0:
            print(f"{i}/{len(groups)} {time.time() - t0:.0f}s", flush=True)
    r = pd.DataFrame(rows)
    print(r.groupby("set")[["rr", "in_cands", "n_cands"]].mean().round(4))
    print("overall MRR@25", round(r.rr.mean(), 4), "| molecules", len(r), f"| {time.time() - t0:.0f}s")
    r.to_csv(os.path.join(a.work, "val_rows.csv"), index=False)


if __name__ == "__main__":
    main()
