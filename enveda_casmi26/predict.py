"""Kaggle entry point: library + fingerprint model ranking, writes submission.csv.

Expects the competition data and our own dataset with cand.pool.parquet, cand.fp.npy and
fpnet.pt (built by fingerprints.py and train_full.py) somewhere under /kaggle/input.
"""

import glob
import time

import numpy as np
import pandas as pd

from .library import build
from .model import make_net
from .rank import Ranker
from .search import Searcher
from .submission import validate


def find(name):
    hits = sorted(glob.glob(f"/kaggle/input/**/{name}", recursive=True), key=len)
    if not hits:
        raise FileNotFoundError(name)
    return hits[0]


def pad(order, ranker, mass, n=25):
    """Pad a short list with the pool structures nearest in mass so every row has guesses."""
    out = list(order)
    if len(out) < n and np.isfinite(mass):
        m = ranker.mass
        i = int(np.searchsorted(m, mass))
        near = sorted(range(max(0, i - n), min(len(m), i + n)), key=lambda j: abs(m[j] - mass))
        have = set(out)
        out += [j for j in near if j not in have][: n - len(out)]
    return out[:n]


def main(train=None, test=None, pool=None, fp=None, weights=None, out="submission.csv"):
    import torch
    t0 = time.time()
    train, test = train or find("train.parquet"), test or find("test.parquet")
    pool = pd.read_parquet(pool or find("cand.pool.parquet"))
    fp = np.load(fp or find("cand.fp.npy"))
    net = make_net(fp.shape[1] * 8)
    net.load_state_dict(torch.load(weights or find("fpnet.pt"), map_location="cpu"))
    lib = build(train)
    print(f"library built {time.time() - t0:.0f}s", flush=True)
    rk, s = Ranker(lib, pool, fp, net), Searcher(lib)
    smiles = pool["smiles"].to_numpy()
    te = pd.read_parquet(test)
    rows = []
    for mid, g in te.groupby("molecule_id", sort=False):
        mass = s.query_mass(g)
        order = pad(rk.rank(g, mass) if np.isfinite(mass) else [], rk, mass)
        rows.append((mid, ";".join(smiles[j] for j in order) if order else "C"))
    sub = pd.DataFrame(rows, columns=["molecule_id", "smiles"])
    problems = validate(sub, te.molecule_id.unique())
    assert not problems, problems
    sub.to_csv(out, index=False)
    print(f"wrote {out}: {len(sub)} molecules, {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
