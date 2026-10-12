# ARC Prize 2026 – ARC-AGI-2

Code competition: the notebook in `kernel/` runs on Kaggle (4×L4, no internet, ≤12 h) and
writes `submission.json`. One submission per day; final deadline 2026-11-02.

- `kernel/` – Kaggle notebook + `kernel-metadata.json`. v1 is an unmodified reproduction of the
  public NVARC-based notebook `mikelou1/arc-agi2-lb33-89-minimal-perfpatch` (public LB 33.89),
  using the public model `sorokin/qwen3_4b_grids15_sft139`.
- `submission.py` – offline schema check and exact-match score for a `submission.json`.

Push and submit:

    kaggle kernels push -p arc_agi2/kernel
    kaggle kernels status danielaijdkx/arc-agi-2-nvarc-baseline
    kaggle competitions submit arc-prize-2026-arc-agi-2 -k danielaijdkx/arc-agi-2-nvarc-baseline -f submission.json -v <version> -m "<note>"
