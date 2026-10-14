"""Train the submission fingerprint model on the whole library (no holdout).

    python -m enveda_casmi26.train_full TRAIN.parquet CAND_PREFIX OUTDIR [--epochs N] [--cap N]
"""

import argparse
import os

import numpy as np
import pandas as pd

from .library import build
from .validate2 import train_net, training_set


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("train")
    ap.add_argument("cand")
    ap.add_argument("out")
    ap.add_argument("--epochs", type=int, default=10)
    ap.add_argument("--cap", type=int, default=700_000)
    a = ap.parse_args()
    import torch
    os.makedirs(a.out, exist_ok=True)
    lib = build(a.train)
    pool = pd.read_parquet(a.cand + ".pool.parquet")
    fp = np.load(a.cand + ".fp.npy")
    idx = pd.Series(np.arange(len(pool)), index=pool.inchikey14)
    idx = idx[~idx.index.duplicated()]
    X, rows, keys = training_set(lib, idx, fp, cap=a.cap)
    del lib
    print("training set", X.shape, flush=True)
    net = train_net(X, rows, fp, keys, a.epochs, log=lambda m: print(m, flush=True))
    torch.save(net.state_dict(), os.path.join(a.out, "fpnet.pt"))


if __name__ == "__main__":
    main()
