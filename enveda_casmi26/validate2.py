"""Validation of library search + fingerprint model on two honest holdouts.

    python -m enveda_casmi26.validate2 TRAIN.parquet CAND_PREFIX WORKDIR [--epochs N]

A (class-1 like): enveda-np-examples structures + 500 enveda-180 structures that also appear in
  another library. Their timsTOF spectra are removed; other libraries' spectra stay.
B (class-2 like): 500 enveda-180 structures found in no other library. All their spectra are
  removed, so the library and the fingerprint model never see them; the structure itself stays
  in the candidate pool, as a PubChem/COCONUT entry would.
Queries use only the test's ten adducts and at most 16 spectra per structure.
"""

import argparse
import os
import time

import numpy as np
import pandas as pd

from .library import Library, build
from .model import ADDUCT_IDX, N_FEAT, featurize, loglik, make_net, predict_proba
from .search import Searcher, cosine

SEED = 0
HOLD_LIBS = {"enveda-np-examples", "enveda-180"}


def holdouts(train):
    t = pd.read_parquet(train, columns=["inchikey14", "ingest_lib"])
    npx = set(t.inchikey14[t.ingest_lib == "enveda-np-examples"])
    e = t.ingest_lib == "enveda-180"
    e_keys, other = set(t.inchikey14[e]), set(t.inchikey14[~e])
    rng = np.random.default_rng(SEED)
    shared = sorted(e_keys & other - npx)
    only = sorted(e_keys - other)
    a = npx | set(rng.choice(shared, 500, replace=False))
    b = set(rng.choice(only, 500, replace=False))
    return a, b


def training_set(lib, fp_index, fp, max_per=4, cap=500_000, seed=SEED):
    s = lib.spectra
    ok = s.adduct.isin(list(ADDUCT_IDX)).to_numpy() & s.inchikey14.isin(fp_index.index).to_numpy()
    idx = np.flatnonzero(ok)
    rng = np.random.default_rng(seed)
    idx = rng.permutation(idx)
    keys = s.inchikey14.to_numpy()[idx]
    _, first = np.unique(keys, return_index=True)
    rank = pd.Series(keys).groupby(keys).cumcount().to_numpy()
    idx = idx[rank < max_per][:cap]
    X = np.zeros((len(idx), N_FEAT), np.float32)
    pmz, add = s.precursor_mz.to_numpy(), s.adduct.to_numpy()
    for r, i in enumerate(idx):
        m, it = lib.peaks(i)
        featurize(m, it, pmz[i], add[i], out=X[r])
    rows = fp_index.loc[s.inchikey14.to_numpy()[idx]].to_numpy()
    return X, rows, s.inchikey14.to_numpy()[idx]


def train_net(X, rows, fp, keys, epochs, log=print, seed=SEED):
    import torch
    torch.manual_seed(seed)
    n_bits = fp.shape[1] * 8
    net = make_net(n_bits)
    opt = torch.optim.Adam(net.parameters(), lr=1e-3)
    lossf = torch.nn.BCEWithLogitsLoss()
    uk = np.unique(keys)
    rng = np.random.default_rng(seed)
    val_keys = set(rng.choice(uk, max(1, len(uk) // 50), replace=False))
    is_val = np.array([k in val_keys for k in keys])
    tr, va = np.flatnonzero(~is_val), np.flatnonzero(is_val)
    Y = lambda r: torch.from_numpy(np.unpackbits(fp[rows[r]], axis=1)[:, :n_bits].astype(np.float32))
    best, best_state = 1e9, None
    for ep in range(epochs):
        net.train()
        perm = rng.permutation(tr)
        t0 = time.time()
        for i in range(0, len(perm), 1024):
            b = perm[i:i + 1024]
            opt.zero_grad()
            loss = lossf(net(torch.from_numpy(X[b])), Y(b))
            loss.backward()
            opt.step()
        net.eval()
        with torch.no_grad():
            vl = float(np.mean([lossf(net(torch.from_numpy(X[va[i:i + 4096]])), Y(va[i:i + 4096])).item()
                                for i in range(0, len(va), 4096)]))
        log(f"epoch {ep + 1}: val BCE {vl:.4f} ({time.time() - t0:.0f}s)")
        if vl < best:
            best, best_state = vl, {k: v.clone() for k, v in net.state_dict().items()}
    net.load_state_dict(best_state)
    return net


def rank_molecule(g, lib, searcher, pool, fp, net, tol_ppm=10.0):
    """Return (pool indices, library cosine, fp loglik) for the candidates of one molecule."""
    mass = searcher.query_mass(g)
    pm = pool["mass"].to_numpy()
    lo = np.searchsorted(pm, mass * (1 - tol_ppm * 1e-6))
    hi = np.searchsorted(pm, mass * (1 + tol_ppm * 1e-6), side="right")
    cand = np.arange(lo, hi)
    if len(cand) == 0:
        return cand, np.zeros(0), np.zeros(0)
    # library cosine for candidates that have library spectra
    lib_sid = pd.Series(np.arange(len(lib.structures)), index=lib.structures.inchikey14)
    qs = []
    from .library import prepare_peaks
    for mzs, ints, mode, pmz, add in zip(g.ms2_mzs, g.ms2_normalized_intensities, g.ionization_mode,
                                         g.precursor_mz, g.adduct):
        q = prepare_peaks(mzs if mzs is not None else [], ints if ints is not None else [])
        if len(q[0]):
            qs.append((q, mode, pmz, add))
    cos = np.zeros(len(cand))
    keys = pool.inchikey14.to_numpy()[cand]
    for j, k in enumerate(keys):
        sid = lib_sid.get(k)
        if sid is None:
            continue
        best = 0.0
        for li in lib.spectra_of(sid):
            lm, lt = lib.peaks(li)
            for (qm, qt), mode, _, _ in qs:
                if mode == searcher.mode[li] and len(lm):
                    best = max(best, cosine(qm, qt, lm, lt, searcher.mz_tol))
        cos[j] = best
    # fingerprint model
    if qs:
        X = np.stack([featurize(qm, qt, pmz, add) for (qm, qt), _, pmz, add in qs])
        p = predict_proba(net, X).mean(0)
        n_bits = len(p)
        bits = np.unpackbits(fp[cand], axis=1)[:, :n_bits].astype(np.float64)
        ll = loglik(p, bits)
    else:
        ll = np.zeros(len(cand))
    return cand, cos, ll


def combine(cos, ll, tau=0.6, beta=0.0):
    """Library hits above tau first (by cosine); the rest by fp log-likelihood (+ beta*cosine)."""
    z = (ll - ll.mean()) / (ll.std() + 1e-9) if len(ll) > 1 else ll * 0
    return np.where(cos >= tau, 10.0 + cos, z + beta * cos)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("train")
    ap.add_argument("cand")
    ap.add_argument("work")
    ap.add_argument("--epochs", type=int, default=6)
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    A, B = holdouts(a.train)
    lp = os.path.join(a.work, "lib_v2")
    if not os.path.exists(lp + ".npz"):
        lib = build(a.train, exclude=lambda m: (m.inchikey14.isin(A).to_numpy()
                                               & m.ingest_lib.isin(HOLD_LIBS).to_numpy())
                    | m.inchikey14.isin(B).to_numpy())
        lib.save(lp)
    lib = Library.load(lp)
    pool = pd.read_parquet(a.cand + ".pool.parquet")
    fp = np.load(a.cand + ".fp.npy")
    fp_index = pd.Series(np.arange(len(pool)), index=pool.inchikey14)
    fp_index = fp_index[~fp_index.index.duplicated()]

    net_path = os.path.join(a.work, "fpnet_v2.pt")
    import torch
    if os.path.exists(net_path):
        net = make_net(fp.shape[1] * 8)
        net.load_state_dict(torch.load(net_path))
    else:
        t0 = time.time()
        X, rows, keys = training_set(lib, fp_index, fp)
        print(f"training set {X.shape} ({time.time() - t0:.0f}s)", flush=True)
        net = train_net(X, rows, fp, keys, a.epochs, log=lambda m: print(m, flush=True))
        torch.save(net.state_dict(), net_path)
        del X

    cols = ["inchikey14", "ingest_lib", "adduct", "ionization_mode", "precursor_mz",
            "ms2_mzs", "ms2_normalized_intensities"]
    q = pd.read_parquet(a.train, columns=cols, filters=[("ingest_lib", "in", sorted(HOLD_LIBS)),
                                                         ("inchikey14", "in", sorted(A | B))])
    q = q[q.adduct.isin(list(ADDUCT_IDX))].groupby("inchikey14").head(16)
    s = Searcher(lib)
    res = []
    for key, g in q.groupby("inchikey14"):
        cand, cos, ll = rank_molecule(g, lib, s, pool, fp, net)
        keys = pool.inchikey14.to_numpy()[cand]
        res.append(dict(key=key, set="A" if key in A else "B", keys=keys, cos=cos, ll=ll))
    pd.to_pickle(res, os.path.join(a.work, "val2_scores.pkl"))

    def mrr(tau, beta):
        out = {}
        for name in ("A", "B"):
            rr = []
            for r in res:
                if r["set"] != name:
                    continue
                order = np.argsort(-combine(r["cos"], r["ll"], tau, beta), kind="stable")[:25]
                hit = np.flatnonzero(r["keys"][order] == r["key"])
                rr.append(1.0 / (hit[0] + 1) if len(hit) else 0.0)
            out[name] = (np.mean(rr), len(rr))
        return out

    for tau in (0.5, 0.6, 0.7, 0.8):
        for beta in (0.0, 1.0, 3.0):
            m = mrr(tau, beta)
            print(f"tau {tau} beta {beta}: A {m['A'][0]:.4f} (n={m['A'][1]})  B {m['B'][0]:.4f} (n={m['B'][1]})")
    inc = [r["key"] in set(r["keys"]) for r in res if r["set"] == "B"]
    print("B: truth in candidate list", np.mean(inc), "| median #cands",
          np.median([len(r["keys"]) for r in res if r["set"] == "B"]))


if __name__ == "__main__":
    main()
