"""Rank candidate structures for one test molecule by spectral similarity to the library.

For each test molecule: neutral mass from its spectra -> library structures within `tol_ppm` ->
score each structure by the best cosine between any of the molecule's spectra and any library
spectrum of that structure in the same ionisation mode -> sort, with how often a structure was
measured as a weak prior and tie-breaker.
"""

import math

import numpy as np

from .chem import neutral_mass
from .library import prepare_peaks

try:
    from numba import njit
except ImportError:  # tests and CI run without numba
    def njit(*a, **k):
        return (lambda f: f) if not (a and callable(a[0])) else a[0]


@njit(cache=True)
def cosine(mz1, i1, mz2, i2, tol):
    """Cosine of two unit-norm, m/z-sorted peak lists; each peak is matched at most once."""
    a = 0
    b = 0
    s = 0.0
    n1 = mz1.shape[0]
    n2 = mz2.shape[0]
    while a < n1 and b < n2:
        d = mz1[a] - mz2[b]
        if d < -tol:
            a += 1
        elif d > tol:
            b += 1
        else:
            # pick the closer of b and b+1 for peak a
            if b + 1 < n2 and abs(mz1[a] - mz2[b + 1]) < abs(d):
                b += 1
            s += i1[a] * i2[b]
            a += 1
            b += 1
    return s


class Searcher:
    def __init__(self, lib, tol_ppm=10.0, mz_tol=0.01, prior=0.02, top_n=25):
        self.lib, self.tol_ppm, self.mz_tol, self.prior, self.top_n = lib, tol_ppm, mz_tol, prior, top_n
        self.mode = lib.spectra["ionization_mode"].to_numpy()

    def query_mass(self, spectra):
        m = [neutral_mass(p, a) for p, a in zip(spectra["precursor_mz"], spectra["adduct"])]
        m = [x for x in m if np.isfinite(x)]
        return float(np.median(m)) if m else float("nan")

    def rank(self, spectra):
        """spectra: DataFrame rows of one molecule. Returns [(structure index, score)] best first."""
        mass = self.query_mass(spectra)
        if not math.isfinite(mass):
            return []
        cands = self.lib.candidates(mass, self.tol_ppm)
        if len(cands) == 0:
            return []
        queries = []
        for mzs, ints, mode, pmz in zip(spectra["ms2_mzs"], spectra["ms2_normalized_intensities"],
                                        spectra["ionization_mode"], spectra["precursor_mz"]):
            q = prepare_peaks(mzs if mzs is not None else [], ints if ints is not None else [])
            if len(q[0]):
                queries.append((q, mode))
        st = self.lib.structures
        out = []
        for sid in cands:
            best = 0.0
            for li in self.lib.spectra_of(sid):
                lm, lt = self.lib.peaks(li)
                if len(lm) == 0:
                    continue
                for (qm, qt), mode in queries:
                    if mode != self.mode[li]:
                        continue
                    c = cosine(qm, qt, lm, lt, self.mz_tol)
                    if c > best:
                        best = c
            score = best + self.prior * math.log1p(st.at[sid, "n_spectra"])
            out.append((int(sid), score))
        out.sort(key=lambda x: -x[1])
        return out[: self.top_n]
