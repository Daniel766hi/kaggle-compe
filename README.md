# DeFi Daily → Kaggle

An automated pipeline that scrapes the free [DefiLlama API](https://defillama.com/docs/api) every day
and publishes a new version of a Kaggle dataset: **DeFi Daily: TVL, Stablecoins, DEX & Yields**.

## What it publishes

| File | Type | Content |
|---|---|---|
| `defi_tvl_history.csv` | full history | Total DeFi TVL per day |
| `chain_tvl_history.csv` | full history | TVL per day for the 25 largest chains |
| `stablecoin_supply_history.csv` | full history | Total stablecoin supply per day |
| `dex_fees_history.csv` | full history | DEX volume and protocol fees per day |
| `protocols_snapshots.parquet` (+ `protocols_latest.csv`) | daily panel | Every protocol's TVL, category, chains |
| `chains_snapshots.parquet` (+ `chains_latest.csv`) | daily panel | Every chain's TVL |
| `stablecoins_snapshots.parquet` (+ `stablecoins_latest.csv`) | daily panel | Every stablecoin's supply and price |
| `yield_pools_snapshots.parquet` (+ `yield_pools_latest.csv`) | daily panel | Yield pools with ≥ $1M TVL |

The **daily panels** are the dataset's unique value: the API only returns the current state, so
each run appends today's snapshot to the panel stored on Kaggle. The longer it runs, the more
valuable the dataset gets.

## How it works

```
GitHub Actions (daily 01:23 UTC)
  └─ python -m defi_dataset
       1. download the current Kaggle version (previous panels)
       2. fetch each DefiLlama endpoint
       3. append today's snapshot / replace full histories
       4. write dataset-metadata.json (description + column docs → high usability score)
       5. upload a new Kaggle version
```

Safety rules:
- Each source is independent. If one endpoint fails, that file is carried forward unchanged and the
  run is marked red so you get an email from GitHub.
- A response with suspiciously few rows, or a history shorter than before, is rejected.
- If the previous version can't be downloaded, nothing is uploaded (so history is never erased).
- Re-running on the same day replaces that day's snapshot instead of duplicating it.

## Setup (one time, about 10 minutes)

1. **Kaggle token**: on kaggle.com → *Settings* → *API* → *Generate New Token*. Copy the token.
2. **GitHub secrets**: in this repo → *Settings* → *Secrets and variables* → *Actions*:
   - Secret `KAGGLE_API_TOKEN` = the token from step 1
     (or, with a legacy `kaggle.json` key: secret `KAGGLE_KEY` = its `key` value)
   - Variable `KAGGLE_USERNAME` = your Kaggle username
   - Optional variable `KAGGLE_DATASET_SLUG` (default `defi-daily-tvl-stablecoins-dex-yields`)
3. **First run**: *Actions* tab → *Update Kaggle dataset* → *Run workflow*.
   The dataset is created **private** so you can review it first.
4. **Review and publish**: open the dataset on Kaggle, add a cover image, check the usability score,
   then set it to **Public** in the dataset settings. Daily runs then add new versions automatically.
   (Or set the variable `KAGGLE_DATASET_PUBLIC=true` before the first run to create it public.)

Note: GitHub pauses scheduled workflows in **public** repos after 60 days without commits. If that
happens, re-enable the workflow in the Actions tab.

## Run locally

```bash
pip install -r requirements.txt
pytest -q                                   # offline tests
python -m defi_dataset --dry-run            # scrape into ./build, no upload
export KAGGLE_USERNAME=... KAGGLE_API_TOKEN=...
python -m defi_dataset                      # scrape and publish
```

## Licence and attribution

Data is from DefiLlama's free public API, credited in the dataset description. The dataset uses
Kaggle's "Other" licence; check DefiLlama's terms of use on their website before making it
public, and update `DATASET_LICENSE` in `defi_dataset/config.py` if needed.

## Code layout

```
defi_dataset/
  config.py       dataset title, slug, thresholds
  schema.py       every table: file name, columns, types, descriptions
  sources.py      HTTP calls to DefiLlama (with retries)
  transform.py    raw JSON → tidy DataFrames (pure, tested)
  storage.py      merge with previous version, write files + metadata
  pipeline.py     builds one version; per-source failure handling
  kaggle_sync.py  download current version, create/version on Kaggle
tests/            offline tests with synthetic API payloads
```
