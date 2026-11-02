# kaggle-compe: project guide for AI agents

Read this before working in the repo. It applies to any agent (Hermes, Claude Code, Codex...).
The README has the full user-facing documentation.

## What this repo is

- `kaggle_pipeline/`: daily pipelines that fetch free public data and publish new versions of
  Kaggle datasets. One module per dataset in `kaggle_pipeline/datasets/`, registered in
  `kaggle_pipeline/datasets/__init__.py`. Table kinds live in `kaggle_pipeline/schema.py`.
- `notebooks/`: one example notebook per dataset, as jupytext percent-format `.py` files.
  `scripts/push_notebooks.py` publishes them to Kaggle.
- `models/<name>/`: `features.py`, `train.py` (time-based test vs baselines), `publish.py`
  (writes the model card from the test results and uploads).
- `x_agent/`, `tiktok_agent/`, `instagram_agent/`, `shorts/`, `office/`: social media content
  agents and the local "office" web UI. `llm.py` is the shared LLM client.
- `.github/workflows/`: scheduled GitHub Actions (`update-dataset.yml` runs the pipelines daily
  at 01:23 UTC; the agent workflows post content).
- `hermes/`: Hermes Agent setup (persona, skills, install scripts). See `hermes/README.md`.

## Commands

```bash
python -m pytest -q                                   # offline test suite, run before every push
python -m kaggle_pipeline <dataset> --dry-run         # build into ./build/<dataset>, no upload
python -m kaggle_pipeline <dataset>                   # fetch and publish (needs Kaggle auth)
python scripts/push_notebooks.py                      # publish notebooks (private by default)
python models/<name>/train.py DATA_DIR OUT_DIR
python models/<name>/publish.py OUT_DIR
```

Use the project virtualenv (`.venv/bin/python` on macOS/Linux, `.venv\Scripts\python.exe` on
Windows) when it exists. Dataset names are the module names with `_` replaced by `-`
(e.g. `idn-weather`, `idr-fx`, `defi`, `movies`).

## Rules for this repo

- **Never upload to Kaggle without being asked.** Use `--dry-run` to test. Real publishing
  creates a new public dataset version.
- **Never erase history.** The pipeline refuses to upload when the previous version can't be
  downloaded or a table shrinks. Don't weaken those checks.
- **Secrets:** keys live in `.env` (gitignored) locally and in GitHub Actions secrets in CI.
  Never commit `.env`, `kaggle.json` or `access_token`. Read keys through `local_env.py`.
- **Tests are offline.** New fetchers get a test with fake responses (see `tests/defi_fakes.py`
  and the other `tests/test_*.py`), never live network calls.
- **Kaggle tags** must be in `KNOWN_KAGGLE_TAGS`, at most 5 per dataset.
- **Content agents** must not invent facts: statistics need a source URL, claims about the user
  must be in the profile files. Nothing posts without approval unless the user turned that on.
- **Adding a dataset:** create the module with a `SPEC = DatasetSpec(...)`, register it, add
  tests, dry-run it, then add it to `matrix.dataset` in `.github/workflows/update-dataset.yml`.
- Match the existing code style: small functions, plain names, short docstrings explaining why.

## Git workflow

- Work on a feature branch, never directly on `main`.
- Run `python -m pytest -q` before pushing. Push with `git push -u origin <branch>`.
- Open a pull request only when the user asks.
