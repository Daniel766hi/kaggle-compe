---
name: kaggle-datasets
description: Run, add, test and publish this repo's Kaggle datasets
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [kaggle, datasets, pipeline, data-engineering, notebooks, models]
    category: kaggle-compe
    requires_toolsets: [terminal]
    related_skills: [careful-engineer, github-workflow]
---

# Kaggle Dataset Pipelines

Operate the `kaggle_pipeline` package in the kaggle-compe repo: dry runs, debugging a failed
daily update, adding a new dataset, publishing notebooks and models.

## When to Use
- "Run / test / fix the <dataset> pipeline", "the daily update failed", "add a dataset for X".
- Publishing or updating example notebooks (`notebooks/`) or models (`models/`).
- Checking what is live on Kaggle.

## Procedure
1. **Auth check:** `kaggle datasets list -m` (lists your own datasets). If it fails with 401,
   the user needs a token: kaggle.com → Settings → API → Generate New Token, saved to
   `~/.kaggle/access_token` (or `KAGGLE_API_TOKEN` in `.env`). Don't handle the token yourself.
2. **Dry run first, always:** `python -m kaggle_pipeline <dataset> --dry-run`
   then inspect `build/<dataset>/` (row counts, date ranges, `dataset-metadata.json`):
   `python -c "import pandas as pd; df=pd.read_csv('build/<d>/<file>.csv'); print(df.shape); print(df.tail())"`
3. **Debug a failed daily run:**
   - `gh run list --workflow update-dataset.yml --limit 5`, then `gh run view <id> --log-failed`.
   - Identify which source failed (each source is independent; the others still published).
   - Reproduce with the dry run, fix the fetcher/transform, add a test with fake responses.
   - Run `python -m pytest -q`, commit on a branch, push. Optionally trigger a CI dry run:
     `gh workflow run update-dataset.yml -f dataset=<dataset> -f dry_run=true`.
4. **Add a dataset** (follow an existing module such as `kaggle_pipeline/datasets/idr_fx.py`):
   1. Find a free, licensed source; note the licence and attribution text.
   2. Create `kaggle_pipeline/datasets/<name>.py` with `SPEC = DatasetSpec(...)`: tables with the
      right kind (`history`, `snapshot`, `incremental`, `derived`), fetchers, description,
      column docs, tags from `KNOWN_KAGGLE_TAGS` (max 5), cover image.
   3. Register it in `kaggle_pipeline/datasets/__init__.py`.
   4. Add `tests/test_<name>.py` using fake HTTP responses (no live network in tests).
   5. Dry run, inspect output, then add the name to `matrix.dataset` in
      `.github/workflows/update-dataset.yml`.
   6. Cover image: `python scripts/make_cover.py` (needs matplotlib).
5. **Publish (only when the user says so):** `python -m kaggle_pipeline <dataset>`.
   New datasets are created private; the user makes them public on kaggle.com.
6. **Notebooks:** `python scripts/push_notebooks.py <name> --dry-run`, then without
   `--dry-run` when asked. Add `--public` only if the dataset it uses is public.
   Check the run: `kaggle kernels status <user>/<slug>`.
7. **Models:** `python models/<m>/train.py DATA_DIR OUT_DIR` (prints test metrics vs
   baselines), then `python models/<m>/publish.py OUT_DIR` when asked.

## Pitfalls
- Weakening the safety checks (row-count guard, "previous version must download") to make a
  run pass. These protect the published history; fix the source problem instead.
- Live network calls inside tests. Use fakes like `tests/defi_fakes.py`.
- Free APIs have rate limits (Open-Meteo, GDELT, NASA FIRMS needs `FIRMS_MAP_KEY`). Incremental
  tables backfill over several runs by design.
- Tags not in `KNOWN_KAGGLE_TAGS` make the metadata update fail.
- Uploading to "test" creates a real public version. Use `--dry-run`.

## Verification
- Dry run finishes and `build/<dataset>/` has the expected files and plausible row counts.
- `python -m pytest -q` passes.
- After a real publish: `kaggle datasets status <user>/<slug>` reports `ready`.
