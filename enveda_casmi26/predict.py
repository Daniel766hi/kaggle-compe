"""Kaggle entry point: build the library from train.parquet, rank candidates, write submission.csv."""

import glob
import os
import time

import numpy as np
import pandas as pd

from .library import build
from .search import Searcher
from .submission import validate


def find(name):
    hits = sorted(glob.glob(f"/kaggle/input/**/{name}", recursive=True), key=len)
    if not hits:
        raise FileNotFoundError(name)
    return hits[0]


def fill(ranked, lib, mass, n=25):
    """Pad a short list with the structures nearest in mass so every row has guesses."""
    have = {sid for sid, _ in ranked}
    out = [sid for sid, _ in ranked]
    if len(out) < n and np.isfinite(mass):
        m = lib.structures["mass"].to_numpy()
        i = int(np.searchsorted(m, mass))
        near = sorted(range(max(0, i - n), min(len(m), i + n)), key=lambda j: abs(m[j] - mass))
        out += [j for j in near if j not in have][: n - len(out)]
    return out[:n]


def main(train=None, test=None, out="submission.csv"):
    t0 = time.time()
    train = train or find("train.parquet")
    test = test or find("test.parquet")
    lib = build(train)
    print(f"library built {time.time() - t0:.0f}s", flush=True)
    te = pd.read_parquet(test)
    s = Searcher(lib)
    smiles = lib.structures["smiles"].to_numpy()
    rows = []
    for mid, g in te.groupby("molecule_id", sort=False):
        ranked = s.rank(g)
        sids = fill(ranked, lib, s.query_mass(g))
        rows.append((mid, ";".join(smiles[j] for j in sids) if sids else "C"))
    sub = pd.DataFrame(rows, columns=["molecule_id", "smiles"])
    problems = validate(sub, te.molecule_id.unique())
    assert not problems, problems
    sub.to_csv(out, index=False)
    print(f"wrote {out}: {len(sub)} molecules, {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
