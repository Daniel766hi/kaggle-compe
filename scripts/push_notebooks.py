"""Publish the example notebooks in notebooks/ to Kaggle.

    pip install jupytext
    export KAGGLE_USERNAME=... KAGGLE_API_TOKEN=...
    python scripts/push_notebooks.py                 # push all, as private notebooks
    python scripts/push_notebooks.py defi --public   # push one, publicly
    python scripts/push_notebooks.py --dry-run       # only build the upload folders

Kaggle runs each notebook after the upload, so its outputs reflect the dataset on that day.
A public notebook can only use public datasets.
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

import jupytext
from slugify import slugify  # installed with the kaggle package

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kaggle_pipeline import kaggle_sync  # noqa: E402

NOTEBOOKS = {
    "defi": {
        "source": "notebooks/defi_market_overview.py",
        "title": "DeFi Market Overview: TVL, Stablecoins, Yields",
        "datasets": ["defi-daily-tvl-stablecoins-dex-yields"],
        "tags": ["finance", "investing", "exploratory data analysis", "data visualization"],
    },
    "idr-fx": {
        "source": "notebooks/rupiah_since_1999.py",
        "title": "Rupiah since 1999: Crises, Trends and Volatility",
        "datasets": ["rupiah-idr-daily-exchange-rates"],
        "tags": ["currencies and foreign exchange", "economics", "time series analysis", "data visualization"],
    },
    "idn-air-quality": {
        "source": "notebooks/indonesia_air_quality.py",
        "title": "Indonesia Air Pollution: 31 Cities Compared",
        "datasets": ["indonesia-air-quality-hourly-pm25", "indonesia-daily-weather-31-cities"],
        "tags": ["pollution", "public health", "exploratory data analysis", "data visualization"],
    },
    "idn-weather": {
        "source": "notebooks/indonesia_weather.py",
        "title": "Indonesia Climate: Rain Seasons and Rising Heat",
        "datasets": ["indonesia-daily-weather-31-cities"],
        "tags": ["weather and climate", "exploratory data analysis", "data visualization"],
    },
    "imdb-sqlite": {
        "source": "notebooks/imdb_sqlite_example.py",
        "title": "IMDb in SQLite: Build and Query in Minutes",
        "datasets": ["imdb-sqlite-database"],
        "internet": True,  # downloads IMDb's files from datasets.imdbws.com
        "tags": ["movies and tv shows", "sql", "data cleaning", "beginner"],
    },
    "haze-forecast": {
        "source": "notebooks/haze_forecast_example.py",
        "title": "Tomorrow's Haze: PM2.5 Forecast for 31 Cities",
        "datasets": ["indonesia-air-quality-hourly-pm25", "indonesia-daily-weather-31-cities",
                     "indonesia-fire-hotspots-nasa-firms"],
        "models": ["indonesia-haze-pm25-next-day/scikitLearn/default/1"],
        "tags": ["pollution", "environment", "time series analysis", "regression"],
    },
    "idn-fires": {
        "source": "notebooks/indonesia_fires_and_haze.py",
        "title": "Indonesia's Fire Seasons from Space, and the Haze",
        "datasets": ["indonesia-fire-hotspots-nasa-firms", "indonesia-air-quality-hourly-pm25"],
        "tags": ["environment", "earth and nature", "pollution", "data visualization"],
    },
    "idn-quakes": {
        "source": "notebooks/indonesia_earthquakes.py",
        "title": "Indonesia's Earthquakes: Where, How Big, What Next",
        "datasets": ["indonesia-earthquakes-usgs-daily"],
        "tags": ["earth and nature", "geography", "exploratory data analysis", "data visualization"],
    },
    "aftershock-forecast": {
        "source": "notebooks/aftershock_forecast_example.py",
        "title": "After a Strong Quake: 7-Day Aftershock Forecast",
        "datasets": ["indonesia-earthquakes-usgs-daily"],
        "models": ["indonesia-aftershock-forecast/scikitLearn/default/2"],
        "tags": ["earth and nature", "time series analysis", "regression", "data visualization"],
    },
    "idn-politics": {
        "source": "notebooks/indonesia_politics_tracker.py",
        "title": "Indonesia's Political Pulse: Protests & Reshuffles",
        "datasets": ["indonesian-political-moves-database-2024-2026"],
        "tags": ["politics", "government", "time series analysis", "data visualization"],
    },
    "movies": {
        "source": "notebooks/movies_oscars_and_recommender.py",
        "title": "Predicting Best Picture + a Movie Recommender",
        "datasets": ["movie-metadata-genre-crew-color-tech-specs"],
        "tags": ["movies and tv shows", "recommender systems", "popular culture", "data visualization"],
    },
}


def build_folder(name, owner, public, folder):
    cfg = NOTEBOOKS[name]
    nb = jupytext.read(ROOT / cfg["source"])
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    code_file = f"{slugify(cfg['title'])}.ipynb"
    jupytext.write(nb, folder / code_file)
    metadata = {
        "id": f"{owner}/{slugify(cfg['title'])}",
        "title": cfg["title"],
        "code_file": code_file,
        "language": "python",
        "kernel_type": "notebook",
        "is_private": not public,
        "enable_gpu": False,
        "enable_internet": cfg.get("internet", False),
        "dataset_sources": [f"{owner}/{d}" for d in cfg["datasets"]],
        "model_sources": [f"{owner}/{m}" for m in cfg.get("models", [])],
        "keywords": cfg["tags"],
    }
    (folder / "kernel-metadata.json").write_text(json.dumps(metadata, indent=2))
    return metadata


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("names", nargs="*", choices=[[]] + sorted(NOTEBOOKS), help="default: all notebooks")
    p.add_argument("--public", action="store_true", help="publish publicly (default: private)")
    p.add_argument("--dry-run", action="store_true", help="build the upload folders without pushing")
    args = p.parse_args()

    owner = os.environ.get("KAGGLE_USERNAME") or sys.exit("Set KAGGLE_USERNAME")
    api = None if args.dry_run else kaggle_sync.get_api()
    for name in args.names or sorted(NOTEBOOKS):
        with tempfile.TemporaryDirectory() as tmp:
            meta = build_folder(name, owner, args.public, Path(tmp))
            if args.dry_run:
                print(f"{name}: built {meta['id']} ({'public' if args.public else 'private'})")
                continue
            resp = api.kernels_push(tmp)
            error = getattr(resp, "error", None)
            if error:
                sys.exit(f"{name}: push failed: {error}")
            print(f"{name}: pushed {getattr(resp, 'url', meta['id'])} ({'public' if args.public else 'private'})")


if __name__ == "__main__":
    main()
