# Enveda CASMI 2026 – Molecule ID from mass spectra

Code competition (notebook, ≤9 h, no internet), metric MRR@25, 5 submissions/day,
final deadline 2026-12-14. Everything here is our own code; no public notebook is reused.
External data: only a raw COCONUT 2021 dump (CC0, Kaggle mirror `thedevastator/open-source-natural-product-annotations`).

| Module | Role |
|---|---|
| `chem.py` | formula → monoisotopic mass, adduct → neutral mass |
| `library.py` | compact spectral library (top-64 peaks per spectrum) from train.parquet |
| `search.py` | cosine scoring of library spectra |
| `fingerprints.py` | candidate pool (train + COCONUT) with Morgan-2048 + MACCS bits (offline, RDKit) |
| `model.py` | spectrum → fingerprint MLP and Bernoulli log-likelihood scoring |
| `rank.py` | combine: library hits (cos ≥ 0.8) first, then fingerprint score |
| `validate.py`, `validate2.py` | local holdouts: A = class-1-like, B = structure known but no spectra |
| `train_full.py`, `predict.py`, `make_kernel.py` | final model, Kaggle entry point, script bundler |

## Results

| Version | Local A (class-1-like) | Local B (no spectra) | Public LB |
|---|---|---|---|
| v1 library search only | 0.894 | 0.000 | 0.150 |
| v2 + fingerprint model, τ = 0.8 | 0.814 | 0.251 | 0.174 |
