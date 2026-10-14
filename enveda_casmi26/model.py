"""Spectrum -> structure-fingerprint model, and candidate scoring with its predictions.

Features of one spectrum (from the library's top-k, sqrt-scaled peaks):
  * fragment intensity in 1 Da bins up to 1000 Da (max per bin),
  * neutral-loss intensity (precursor m/z - fragment m/z) in 1 Da bins up to 300 Da,
  * adduct one-hot and precursor neutral mass / 1000.
A small MLP predicts the 2215 fingerprint bits; a candidate's score is the Bernoulli
log-likelihood of its fingerprint under the averaged prediction of the molecule's spectra.
"""

import numpy as np

from .chem import neutral_mass

N_FRAG, N_LOSS = 1000, 300
ADDUCT_LIST = ["[M+H]+", "[M+NH4]+", "[M-H2O+H]+", "[M-2H2O+H]+", "[M+Na]+", "[M+K]+",
               "[M-H]-", "[M-H2O-H]-", "[M+CH2O2-H]-", "[M+Cl]-"]
ADDUCT_IDX = {a: i for i, a in enumerate(ADDUCT_LIST)}
N_FEAT = N_FRAG + N_LOSS + len(ADDUCT_LIST) + 1 + 1


def featurize(mz, inten, precursor_mz, adduct, out=None):
    x = np.zeros(N_FEAT, np.float32) if out is None else out
    mz = np.asarray(mz, np.float64)
    it = np.asarray(inten, np.float32)
    f = np.floor(mz).astype(np.int64)
    ok = (f >= 0) & (f < N_FRAG)
    np.maximum.at(x, f[ok], it[ok])
    loss = np.floor(precursor_mz - mz).astype(np.int64)
    ok = (loss >= 0) & (loss < N_LOSS)
    np.maximum.at(x, N_FRAG + loss[ok], it[ok])
    x[N_FRAG + N_LOSS + ADDUCT_IDX.get(adduct, len(ADDUCT_LIST))] = 1.0
    m = neutral_mass(precursor_mz, adduct)
    x[-1] = (m if np.isfinite(m) else precursor_mz) / 1000.0
    return x


def make_net(n_bits, hidden=1024, dropout=0.2):
    import torch.nn as nn
    return nn.Sequential(
        nn.Linear(N_FEAT, hidden), nn.ReLU(), nn.Dropout(dropout),
        nn.Linear(hidden, hidden), nn.ReLU(), nn.Dropout(dropout),
        nn.Linear(hidden, n_bits),
    )


def predict_proba(net, X, batch=4096):
    import torch
    net.eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(X), batch):
            out.append(torch.sigmoid(net(torch.from_numpy(X[i:i + batch]))).numpy())
    return np.concatenate(out) if out else np.zeros((0, net[-1].out_features), np.float32)


def loglik(p, fp_bits):
    """p: (n_bits,) probabilities; fp_bits: (n_cand, n_bits) 0/1. Higher is better."""
    p = np.clip(p.astype(np.float64), 1e-4, 1 - 1e-4)
    lp, lq = np.log(p), np.log1p(-p)
    return fp_bits @ (lp - lq) + lq.sum()
