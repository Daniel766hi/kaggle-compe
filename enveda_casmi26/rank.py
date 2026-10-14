"""Candidate generation and scoring shared by validation and the Kaggle entry point.

Candidates are pool structures (train + COCONUT) within `tol_ppm` of the molecule's neutral mass.
Each gets (a) the best library cosine against its own library spectra, if any, and (b) the
fingerprint-model log-likelihood. Library hits with cosine >= tau come first; the rest are
ordered by the standardised fingerprint score.
"""

import numpy as np
import pandas as pd

from .library import prepare_peaks
from .model import featurize, loglik, predict_proba
from .search import cosine

TAU = 0.8


class Ranker:
    def __init__(self, lib, pool, fp, net, tol_ppm=10.0, mz_tol=0.01, tau=TAU):
        self.lib, self.pool, self.fp, self.net = lib, pool, fp, net
        self.tol_ppm, self.mz_tol, self.tau = tol_ppm, mz_tol, tau
        self.mass = pool["mass"].to_numpy()
        self.keys = pool["inchikey14"].to_numpy()
        self.lib_sid = pd.Series(np.arange(len(lib.structures)), index=lib.structures.inchikey14).to_dict()
        self.mode = lib.spectra["ionization_mode"].to_numpy()
        self.n_bits = net[-1].out_features

    def candidates(self, mass):
        lo = np.searchsorted(self.mass, mass * (1 - self.tol_ppm * 1e-6))
        hi = np.searchsorted(self.mass, mass * (1 + self.tol_ppm * 1e-6), side="right")
        return np.arange(lo, hi)

    def score(self, g, mass):
        """g: spectra rows of one molecule. Returns (pool indices, cosine, fp log-likelihood)."""
        cand = self.candidates(mass)
        qs = []
        for mzs, ints, mode, pmz, add in zip(g["ms2_mzs"], g["ms2_normalized_intensities"],
                                             g["ionization_mode"], g["precursor_mz"], g["adduct"]):
            q = prepare_peaks(mzs if mzs is not None else [], ints if ints is not None else [])
            if len(q[0]):
                qs.append((q, mode, pmz, add))
        cos = np.zeros(len(cand))
        ll = np.zeros(len(cand))
        if len(cand) == 0 or not qs:
            return cand, cos, ll
        for j, k in enumerate(self.keys[cand]):
            sid = self.lib_sid.get(k)
            if sid is None:
                continue
            best = 0.0
            for li in self.lib.spectra_of(sid):
                lm, lt = self.lib.peaks(li)
                if not len(lm):
                    continue
                for (qm, qt), mode, _, _ in qs:
                    if mode == self.mode[li]:
                        c = cosine(qm, qt, lm, lt, self.mz_tol)
                        if c > best:
                            best = c
            cos[j] = best
        X = np.stack([featurize(qm, qt, pmz, add) for (qm, qt), _, pmz, add in qs])
        p = predict_proba(self.net, X).mean(0)
        bits = np.unpackbits(self.fp[cand], axis=1)[:, :self.n_bits].astype(np.float64)
        ll = loglik(p, bits)
        return cand, cos, ll

    def rank(self, g, mass, top_n=25):
        cand, cos, ll = self.score(g, mass)
        order = np.argsort(-combine(cos, ll, self.tau), kind="stable")[:top_n]
        return cand[order]


def combine(cos, ll, tau=TAU, beta=0.0):
    """Library hits above tau first (by cosine); the rest by standardised fp log-likelihood."""
    z = (ll - ll.mean()) / (ll.std() + 1e-9) if len(ll) > 1 else ll * 0
    return np.where(cos >= tau, 10.0 + cos, z + beta * cos)
