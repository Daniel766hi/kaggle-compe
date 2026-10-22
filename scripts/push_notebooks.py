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
    "idn-fires": {
        "source": "notebooks/indonesia_fires_and_haze.py",
        "title": "Indonesia's Fire Seasons from Space, and the Haze",
        "datasets": ["indonesia-fire-hotspots-nasa-firms", "indonesia-air-quality-hourly-pm25"],
        "tags": ["environment", "earth and nature", "pollution", "data visualization"],
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
    "nfl-bdb-2027": {
        "source": "notebooks/nfl_bdb2027_combine_engine.py",
        "title": "How Many NFL Games Is the Combine Worth?",
        "datasets": [],
        "competitions": ["nfl-big-data-bowl-2027"],
        "inline": ["nfl_bdb2027/movement.py", "nfl_bdb2027/build_features.py"],
        "tags": ["sports", "american football", "data visualization"],
    },
    "nfl-bdb-2027-turning": {
        "source": "notebooks/nfl_bdb2027_turning_engine.py",
        "title": "Bend, Don't Brake: The Turning Engine",
        "datasets": [],
        "competitions": ["nfl-big-data-bowl-2027"],
        "inline": ["nfl_bdb2027/movement.py", "nfl_bdb2027/build_features.py"],
        "tags": ["sports", "american football", "data visualization"],
    },
}


def inline_modules(nb, paths):
    """Paste local modules into the notebook so it runs on Kaggle, where the repo is not installed.

    The module code replaces the cell's `# INLINE:` marker; imports of the package are dropped
    everywhere, and each module's `if __name__ == "__main__":` block is cut off.
    """
    code = []
    for path in paths:
        src = (ROOT / path).read_text().split('\nif __name__ == "__main__":')[0]
        code.append(f"# ---- {path} ----\n{src.strip()}\n")
    for cell in nb.cells:
        if cell.cell_type != "code":
            continue
        src = "\n".join("\n".join(code) if ln.startswith("# INLINE:") else ln for ln in cell.source.splitlines())
        cell.source = "\n".join(ln for ln in src.splitlines() if not ln.startswith("from nfl_bdb2027"))
    return nb


def build_folder(name, owner, public, folder):
    cfg = NOTEBOOKS[name]
    nb = jupytext.read(ROOT / cfg["source"])
    if cfg.get("inline"):
        nb = inline_modules(nb, cfg["inline"])
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
        "enable_internet": False,
        "dataset_sources": [f"{owner}/{d}" for d in cfg["datasets"]],
        "competition_sources": cfg.get("competitions", []),
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
