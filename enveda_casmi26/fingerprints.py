"""Candidate pool (train structures + a raw COCONUT dump) with packed structure fingerprints.

    python -m enveda_casmi26.fingerprints TRAIN_META.parquet COCONUT.csv OUT_PREFIX [EXTRA.smi ...]

EXTRA files are plain lists of SMILES (one per line) from other raw databases; their InChIKey-14
and formula are computed here with RDKit.

Writes OUT_PREFIX.pool.parquet (inchikey14, smiles, formula, mass, in_train) and
OUT_PREFIX.fp.npy (uint8, packed bits: Morgan radius 2 / 2048 bits + 167 MACCS keys).
Needs RDKit; runs offline, the Kaggle notebook only reads the outputs.
"""

import sys
from multiprocessing import Pool

import numpy as np
import pandas as pd

from .chem import formula_mass

N_MORGAN = 2048
N_MACCS = 167
N_BITS = N_MORGAN + N_MACCS


def fp_bits(smiles):
    from rdkit import Chem, RDLogger
    from rdkit.Chem import MACCSkeys, rdFingerprintGenerator
    RDLogger.DisableLog("rdApp.*")
    out = np.zeros(N_BITS, np.uint8)
    m = Chem.MolFromSmiles(smiles) if isinstance(smiles, str) else None
    if m is None:
        return None
    gen = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=N_MORGAN)
    out[list(gen.GetFingerprint(m).GetOnBits())] = 1
    out[N_MORGAN + np.array(list(MACCSkeys.GenMACCSKeys(m).GetOnBits()), dtype=int)] = 1
    return np.packbits(out)


def _batch(smiles):
    return [fp_bits(s) for s in smiles]


def describe(smiles):
    """SMILES -> (inchikey14, canonical smiles, formula) or None; neutral, single-fragment only."""
    from rdkit import Chem, RDLogger
    from rdkit.Chem.rdMolDescriptors import CalcMolFormula
    RDLogger.DisableLog("rdApp.*")
    m = Chem.MolFromSmiles(smiles) if isinstance(smiles, str) and smiles else None
    if m is None or len(Chem.GetMolFrags(m)) != 1 or Chem.GetFormalCharge(m) != 0:
        return None
    ik = Chem.MolToInchiKey(m)
    return (ik[:14], Chem.MolToSmiles(m), CalcMolFormula(m)) if ik else None


def _describe_batch(smiles):
    return [describe(s) for s in smiles]


def extra_pool(paths):
    smiles = sorted({ln.strip() for p in paths for ln in open(p) if ln.strip()})
    chunks = [smiles[i:i + 2000] for i in range(0, len(smiles), 2000)]
    with Pool() as p:
        rows = [r for part in p.imap(_describe_batch, chunks) for r in part if r]
    return pd.DataFrame(rows, columns=["inchikey14", "smiles", "formula"]).drop_duplicates("inchikey14")


def build_pool(train_meta, coconut_csv, extra=()):
    t = pd.read_parquet(train_meta, columns=["inchikey14", "normalized_smiles", "molecular_formula"])
    tr = (t.groupby("inchikey14").agg(smiles=("normalized_smiles", lambda s: s.value_counts().index[0]),
                                       formula=("molecular_formula", "first")).reset_index())
    tr["in_train"] = True
    c = pd.read_csv(coconut_csv, usecols=[1, 2, 4], header=0, names=["formula", "smiles", "inchikey"])
    c["inchikey14"] = c.inchikey.astype(str).str[:14]
    c = c[~c.inchikey14.isin(set(tr.inchikey14))].drop_duplicates("inchikey14")
    c = c[["inchikey14", "smiles", "formula"]].assign(in_train=False)
    parts = [tr, c]
    if extra:
        e = extra_pool(extra)
        e = e[~e.inchikey14.isin(set(tr.inchikey14) | set(c.inchikey14))].assign(in_train=False)
        print(f"extra sources: {len(e)} new structures")
        parts.append(e)
    pool = pd.concat(parts, ignore_index=True)
    pool["mass"] = [formula_mass(f) for f in pool.formula]
    return pool[np.isfinite(pool["mass"])].reset_index(drop=True)


def main(train_meta, coconut_csv, out, *extra):
    pool = build_pool(train_meta, coconut_csv, extra)
    smiles = pool.smiles.tolist()
    chunks = [smiles[i:i + 2000] for i in range(0, len(smiles), 2000)]
    with Pool() as p:
        fps = [f for part in p.imap(_batch, chunks) for f in part]
    ok = np.array([f is not None for f in fps])
    pool = pool[ok].sort_values("mass", kind="stable")
    fp = np.stack([fps[i] for i in pool.index])
    pool = pool.reset_index(drop=True)
    pool.to_parquet(f"{out}.pool.parquet")
    np.save(f"{out}.fp.npy", fp)
    print(f"pool {len(pool)} ({pool.in_train.sum()} from train), fp {fp.shape}, dropped {(~ok).sum()}")


if __name__ == "__main__":
    main(*sys.argv[1:])
