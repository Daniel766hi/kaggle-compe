# Enveda CASMI 2026 – Molecule ID from mass spectra

Code competition (notebook, ≤9 h, no internet), metric MRR@25, 5 submissions/day,
final deadline 2026-12-14.

- `toppublic_cpu/` – CPU-only reproduction of the public notebook `spark328/casmi26-top-public`.
- `e006/`, `dualband/` – GPU reproductions of `canqiang/casmi26-e006-window-40-ice-fallback-true`
  (public LB 0.440) and `saddamaditya/casmi26-dual-band-massbank-iceberg-sota`; these need the
  weekly Kaggle GPU quota.
- `submission.py` – offline check of `submission.csv` against the Evaluation-page rules.

All notebooks credit and reuse the public datasets listed in their `kernel-metadata.json`.
