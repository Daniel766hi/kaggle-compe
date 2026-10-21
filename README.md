# Kaggle datasets, updated automatically

Automated pipelines that pull free public data every day and publish a new version of each
Kaggle dataset. One GitHub Actions workflow runs them all.

| Dataset | Command name | Source | Updates |
|---|---|---|---|
| [DeFi Daily: TVL, Stablecoins, DEX & Yields](https://www.kaggle.com/datasets/danielaijdkx/defi-daily-tvl-stablecoins-dex-yields) | `defi` | DefiLlama API | daily |
| [Indonesia Air Quality: Hourly PM2.5, 31 Cities](https://www.kaggle.com/datasets/danielaijdkx/indonesia-air-quality-hourly-pm25) | `idn-air-quality` | Open-Meteo (CAMS), CC BY 4.0 | daily |
| [Indonesia Daily Weather: 31 Cities since 2000](https://www.kaggle.com/datasets/danielaijdkx/indonesia-daily-weather-31-cities) | `idn-weather` | Open-Meteo (ERA5), CC BY 4.0 | daily |
| [Rupiah (IDR) Daily Exchange Rates](https://www.kaggle.com/datasets/danielaijdkx/rupiah-idr-daily-exchange-rates) | `idr-fx` | ECB reference rates via Frankfurter | daily |
| [Indonesia Fire Hotspots (NASA FIRMS, daily)](https://www.kaggle.com/datasets/danielaijdkx/indonesia-fire-hotspots-nasa-firms) | `idn-fires` | NASA FIRMS VIIRS active fires (needs the free `FIRMS_MAP_KEY` secret), geoBoundaries | daily |
| [Indonesia Politics Tracker: Events & Cabinet](https://www.kaggle.com/datasets/danielaijdkx/indonesian-political-moves-database-2024-2026) | `idn-politics` | GDELT events, Wikipedia cabinet tables (CC BY-SA) | daily |
| [Movie Metadata: Genre, Crew, Color & Tech Specs](https://www.kaggle.com/datasets/danielaijdkx/movie-metadata-genre-crew-color-tech-specs) | `movies` | Wikidata (CC0) | weekly (Mondays) |

## How it works

```
GitHub Actions (daily 01:23 UTC = 08:23 WIB), one job per dataset
  └─ python -m kaggle_pipeline <dataset>
       1. download the dataset's current Kaggle version
       2. fetch each source table
       3. merge: replace full histories, append daily snapshots, or upsert new date ranges
       4. compute derived tables (daily/monthly summaries)
       5. write dataset-metadata.json (description, file/column docs, sources, update frequency)
       6. upload a new Kaggle version, then update the dataset settings (cover image, docs)
```

Table kinds (see `kaggle_pipeline/schema.py`):
- **history**: the source returns the full series, so the file is rebuilt every run (DeFi, FX).
- **snapshot**: the source only returns today's state, so each run appends a dated snapshot (DeFi panels).
- **incremental**: the source has history but too much to refetch daily, so each run fetches the
  recent window plus older ranges until a request budget is spent (Open-Meteo). History back to
  2000 (weather) or 2022 (air quality) fills in over the first few runs within the free API limits.
- **derived**: computed from the other tables (daily air quality summary, monthly weather, IDR cross rates).

Safety rules:
- Each source is independent. If one fails, its previous file is carried forward unchanged and the
  run is marked red so GitHub emails you. One dataset failing never stops the others.
- A response with suspiciously few rows, or a table smaller than before, is rejected.
- If the previous version can't be downloaded, nothing is uploaded, so history is never erased.
- Re-running on the same day replaces that day's data instead of duplicating it.
- Public/private visibility is kept as you set it on kaggle.com.

## Setup (one time)

1. **Kaggle token**: kaggle.com → *Settings* → *API* → *Generate New Token*.
2. **GitHub**: this repo → *Settings* → *Secrets and variables* → *Actions*:
   - Secret `KAGGLE_API_TOKEN` = the token (or, with a legacy `kaggle.json` key: secret `KAGGLE_KEY`)
   - Variable `KAGGLE_USERNAME` = your Kaggle username
3. **Run**: *Actions* → *Update Kaggle datasets* → *Run workflow*. New datasets are created
   **private**; review them on Kaggle and make them public in the dataset settings.
   A manual run can target one dataset (e.g. `idn-weather`) and can be a **dry run**, which
   builds and logs the files without uploading anything.

GitHub pauses scheduled workflows in **public** repos after 60 days without commits. If that
happens, re-enable the workflow in the Actions tab.

## Run locally

```bash
pip install -r requirements.txt
pytest -q                                          # offline tests
python -m kaggle_pipeline idr-fx --dry-run         # fetch into ./build/idr-fx, no upload
export KAGGLE_USERNAME=... KAGGLE_API_TOKEN=...
python -m kaggle_pipeline idr-fx                   # fetch and publish
```

## Example notebooks

`notebooks/` holds one example notebook per dataset, written as readable `.py` files
(jupytext percent format). `scripts/push_notebooks.py` converts them and publishes them to Kaggle,
where they run against the current data. They are pushed private by default; add `--public` once
the dataset they use is public.

| Notebook | What it shows |
|---|---|
| `defi_market_overview.py` | DeFi TVL, stablecoins, DEX volume and yields |
| `rupiah_since_1999.py` | Rupiah crises, trends and volatility |
| `indonesia_air_quality.py` | PM2.5 across 31 cities |
| `indonesia_weather.py` | Rain seasons and warming |
| `indonesia_fires_and_haze.py` | Worst fire years, the fire calendar, provinces, 2026 vs past seasons, fires vs PM2.5 in nearby cities |
| `indonesia_politics_tracker.py` | Protest waves, where protests happen, cabinet reshuffles and unrest before them |
| `nfl_bdb2027_combine_engine.py` | NFL Big Data Bowl 2027 entry: Combine vs. in-game sprint profiles, how many games the Combine is worth, per-play engine utilization (uses competition data; see `bdb2027_writeup/`) |
| `movies_oscars_and_recommender.py` | Best Picture nomination/winner prediction (time-based backtest, blind test on the 2026 ceremony, forecast for 2026 films) and an explainable content-based movie recommender |

## Adding a dataset

Create `kaggle_pipeline/datasets/<name>.py` with a `SPEC = DatasetSpec(...)` (tables, fetchers,
description, cover image), register it in `kaggle_pipeline/datasets/__init__.py`, test it with a
manual dry run, then add its name to the scheduled list in the workflow's `matrix.dataset`.
Tags must be Kaggle tags (see `KNOWN_KAGGLE_TAGS`, at most 5). Cover images are drawn from real data with
`scripts/make_cover.py` (needs `pip install matplotlib`).

## Licences and attribution

Each dataset's description credits its source. DeFi data is from DefiLlama's free API (licence
"Other"); Open-Meteo data is CC BY 4.0 (with Copernicus/ECMWF attribution); ECB reference rates
may be reused with the source acknowledged.

## Code layout

```
kaggle_pipeline/
  schema.py        Column, Table, DatasetSpec
  frames.py        type conversion and de-duplication shared by all tables
  storage.py       merge with the previous version, write files + metadata
  pipeline.py      builds one version; per-source failure handling; derived tables
  kaggle_sync.py   download current version, create/version on Kaggle, settings update
  http.py          HTTP session with retries
  datasets/
    defi/              DefiLlama (tables, sources, transforms)
    open_meteo.py      cities, request planning and rate-limit budget for Open-Meteo
    idn_air_quality.py
    idn_weather.py
    idr_fx.py
    movies.py          Wikidata movie metadata
    idn_politics.py    GDELT events in Indonesia + cabinet terms from Wikipedia
    idn_fires.py       NASA FIRMS fire detections in Indonesia, by province
tests/             offline tests with synthetic API payloads
```
