---
name: kaggle-competition
description: "Kaggle competition loop: validation, experiments, submit"
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [kaggle, competition, machine-learning, cross-validation, submission]
    category: kaggle-compe
    requires_toolsets: [terminal]
    related_skills: [careful-engineer]
---

# Kaggle Competition Workflow

Take a Kaggle competition from zero to a validated baseline and disciplined improvements,
with experiments tracked and submissions made only with the user's go-ahead.

## When to Use
- "Join / start / work on the <competition> competition", "build a baseline", "improve my score".
- Any tabular, time-series, NLP or vision competition run through the Kaggle CLI.

## Procedure
1. **Read the competition.** `kaggle competitions list -s "<keywords>"` to get the slug, then
   read the Overview, Evaluation metric, Data and Rules pages (web tools). Write down:
   metric, target, submission format, deadline, daily submission limit, external data rules,
   whether it is a code competition (submit via notebook).
2. **Rules acceptance** is done by the user on the website ("Join Competition"). A 403 on
   download means they haven't accepted yet: tell them.
3. **Download:** `kaggle competitions download -c <slug> -p data/<slug>` then unzip.
   Keep data out of git (add `data/` to `.gitignore` if missing).
4. **Understand the data (EDA):** shapes, dtypes, missing values, target distribution,
   train/test differences (dates, IDs, categories present only in test), duplicates, leaks.
   Summarise findings in `experiments/<slug>/NOTES.md`.
5. **Validation that matches the test split.** This is the most important step.
   - Time-based data: time-ordered split (no shuffling into the future).
   - Grouped data (same user/patient/store in many rows): `GroupKFold`.
   - Imbalanced classification: `StratifiedKFold`.
   - Fit preprocessing inside each fold only. Fix seeds.
6. **Baseline first:** the simplest sensible model (e.g. mean/majority, then LightGBM or
   logistic regression on raw features). Record CV score ± std.
7. **Iterate one change at a time.** Features, then model, then tuning, then ensembling.
   Log every experiment in `experiments/<slug>/log.csv`: date, change, CV mean, CV std,
   public LB (if submitted). Keep a change only if CV improves beyond noise.
8. **Submit (ask first; submissions are limited per day):**
   - Check the file matches `sample_submission.csv` (columns, row count, ID order, no NaN).
   - `kaggle competitions submit -c <slug> -f submission.csv -m "<experiment id + CV>"`.
   - `kaggle competitions submissions -c <slug>` to read the score.
   - Code competitions: push a notebook with `kaggle kernels push -p <dir>` and submit from it.
9. **Trust CV over public LB.** The public leaderboard is a small sample. Final selection: the
   best CV model plus one diverse, robust alternative.
10. **Report** to the user: current CV and LB, what helped, what didn't, next ideas ranked by
    expected gain vs effort.

## Pitfalls
- Leakage: target-derived features, future information, fitting scalers/encoders on all data.
- Validation that doesn't mirror the test split, so CV and LB disagree.
- Overfitting the public leaderboard by submitting many small tweaks.
- Using external data or pretrained models the rules forbid.
- Committing competition data to git (often forbidden by the rules, and large).

## Verification
- CV is reproducible: rerunning with the same seed gives the same score.
- Submission file passes a format check against `sample_submission.csv` before upload.
- Every submitted file maps to a row in `experiments/<slug>/log.csv`.
