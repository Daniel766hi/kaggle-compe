"""Candidate pool (train structures + a raw COCONUT dump) with packed structure fingerprints.

    python -m enveda_casmi26.fingerprints TRAIN_META.parquet COCONUT.csv OUT_PREFIX

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


def build_pool(train_meta, coconut_csv):
    t = pd.read_parquet(train_meta, columns=["inchikey14", "normalized_smiles", "molecular_formula"])
    tr = (t.groupby("inchikey14").agg(smiles=("normalized_smiles", lambda s: s.value_counts().index[0]),
                                       formula=("molecular_formula", "first")).reset_index())
    tr["in_train"] = True
    c = pd.read_csv(coconut_csv, usecols=[1, 2, 4], header=0, names=["formula", "smiles", "inchikey"])
    c["inchikey14"] = c.inchikey.astype(str).str[:14]
    c = c[~c.inchikey14.isin(set(tr.inchikey14))].drop_duplicates("inchikey14")
    c = c[["inchikey14", "smiles", "formula"]].assign(in_train=False)
    pool = pd.concat([tr, c], ignore_index=True)
    pool["mass"] = [formula_mass(f) for f in pool.formula]
    return pool[np.isfinite(pool["mass"])].reset_index(drop=True)


def main(train_meta, coconut_csv, out):
    pool = build_pool(train_meta, coconut_csv)
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
    main(*sys.argv[1:4])
