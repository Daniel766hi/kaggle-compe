"""Compact spectral library built from train.parquet.

Each spectrum keeps its `TOP_K` most intense peaks, with sqrt intensities scaled to unit norm, in
flat float32 arrays (`mz`, `inten`) addressed by `offsets`. A structure table (one row per
InChIKey-14) carries the SMILES, formula, monoisotopic mass and how often it was measured.
"""

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from .chem import formula_mass, neutral_mass

TOP_K = 64
META_COLS = ["inchikey14", "normalized_smiles", "molecular_formula", "adduct", "ionization_mode",
             "precursor_mz", "ingest_lib", "instrument_type"]


def prepare_peaks(mzs, ints, top_k=TOP_K, max_mz=None):
    """Keep the top_k peaks (optionally below max_mz), sorted by m/z, sqrt-scaled to unit norm."""
    mz = np.asarray(mzs, dtype=np.float64)
    it = np.asarray(ints, dtype=np.float64)
    ok = np.isfinite(mz) & np.isfinite(it) & (it > 0)
    if max_mz is not None:
        ok &= mz <= max_mz
    mz, it = mz[ok], it[ok]
    if len(it) > top_k:
        keep = np.argpartition(-it, top_k - 1)[:top_k]
        mz, it = mz[keep], it[keep]
    order = np.argsort(mz)
    mz, it = mz[order], np.sqrt(it[order])
    norm = np.sqrt((it ** 2).sum())
    if norm > 0:
        it = it / norm
    return mz.astype(np.float32), it.astype(np.float32)


class Library:
    def __init__(self, spectra, mz, inten, offsets, structures):
        self.spectra = spectra          # DataFrame, one row per spectrum, column `sid` = structure index
        self.mz, self.inten, self.offsets = mz, inten, offsets
        self.structures = structures    # DataFrame indexed 0..n-1, sorted by `mass`
        order = np.argsort(spectra["sid"].to_numpy(), kind="stable")
        self._by_struct = order
        counts = np.bincount(spectra["sid"].to_numpy(), minlength=len(structures))
        self._struct_start = np.concatenate([[0], np.cumsum(counts)])

    def peaks(self, i):
        a, b = self.offsets[i], self.offsets[i + 1]
        return self.mz[a:b], self.inten[a:b]

    def spectra_of(self, sid):
        return self._by_struct[self._struct_start[sid]:self._struct_start[sid + 1]]

    def candidates(self, mass, tol_ppm):
        m = self.structures["mass"].to_numpy()
        lo = np.searchsorted(m, mass * (1 - tol_ppm * 1e-6))
        hi = np.searchsorted(m, mass * (1 + tol_ppm * 1e-6), side="right")
        return np.arange(lo, hi)

    # ---- persistence -------------------------------------------------------------------
    def save(self, path):
        np.savez(path, mz=self.mz, inten=self.inten, offsets=self.offsets)
        self.spectra.to_parquet(f"{path}.spectra.parquet")
        self.structures.to_parquet(f"{path}.structures.parquet")

    @classmethod
    def load(cls, path):
        z = np.load(f"{path}.npz" if not str(path).endswith(".npz") else path)
        base = str(path).removesuffix(".npz")
        return cls(pd.read_parquet(f"{base}.spectra.parquet"), z["mz"], z["inten"], z["offsets"],
                   pd.read_parquet(f"{base}.structures.parquet"))


def build(train_path, exclude=None, top_k=TOP_K, log=print):
    """Read train.parquet row group by row group. `exclude(meta_df) -> bool mask` drops rows."""
    pf = pq.ParquetFile(train_path)
    metas, mzs, ints, lens = [], [], [], []
    for g in range(pf.num_row_groups):
        tb = pf.read_row_group(g, columns=META_COLS + ["ms2_mzs", "ms2_normalized_intensities"])
        meta = tb.select(META_COLS).to_pandas()
        keep = np.ones(len(meta), bool) if exclude is None else ~np.asarray(exclude(meta))
        pm = tb.column("ms2_mzs").to_pylist()
        pi = tb.column("ms2_normalized_intensities").to_pylist()
        for j in np.flatnonzero(keep):
            a, b = prepare_peaks(pm[j] or [], pi[j] or [], top_k)
            mzs.append(a); ints.append(b); lens.append(len(a))
        metas.append(meta[keep])
        if g % 20 == 0:
            log(f"row group {g + 1}/{pf.num_row_groups}, spectra so far {len(lens)}")
    spectra = pd.concat(metas, ignore_index=True)
    offsets = np.concatenate([[0], np.cumsum(lens)]).astype(np.int64)
    mz = np.concatenate(mzs) if mzs else np.zeros(0, np.float32)
    inten = np.concatenate(ints) if ints else np.zeros(0, np.float32)

    g = spectra.groupby("inchikey14", sort=False)
    st = pd.DataFrame({
        "inchikey14": g.size().index,
        "smiles": g["normalized_smiles"].agg(lambda s: s.value_counts().index[0]).to_numpy(),
        "formula": g["molecular_formula"].first().to_numpy(),
        "n_spectra": g.size().to_numpy(),
        "n_libs": g["ingest_lib"].nunique().to_numpy(),
    })
    st["mass"] = [formula_mass(f) for f in st.formula]
    # fall back to the median precursor-implied mass when the formula can't be parsed
    bad = ~np.isfinite(st["mass"].to_numpy())
    if bad.any():
        nm = pd.Series([neutral_mass(p, a) for p, a in zip(spectra.precursor_mz, spectra.adduct)])
        med = nm.groupby(spectra.inchikey14).median()
        st.loc[bad, "mass"] = st.loc[bad, "inchikey14"].map(med).to_numpy()
    st = st[np.isfinite(st["mass"])].sort_values("mass", kind="stable").reset_index(drop=True)
    sid = pd.Series(np.arange(len(st)), index=st.inchikey14)
    spectra["sid"] = spectra.inchikey14.map(sid)
    ok = spectra["sid"].notna().to_numpy()
    if not ok.all():  # drop spectra whose structure has no usable mass
        idx = np.flatnonzero(ok)
        new_off = [0]
        parts_mz, parts_in = [], []
        for i in idx:
            a, b = offsets[i], offsets[i + 1]
            parts_mz.append(mz[a:b]); parts_in.append(inten[a:b]); new_off.append(new_off[-1] + b - a)
        mz, inten = np.concatenate(parts_mz), np.concatenate(parts_in)
        offsets = np.asarray(new_off, np.int64)
        spectra = spectra[ok].reset_index(drop=True)
    spectra["sid"] = spectra["sid"].astype(np.int64)
    log(f"library: {len(spectra)} spectra, {len(st)} structures, {len(mz)} peaks")
    return Library(spectra, mz, inten, offsets, st)
