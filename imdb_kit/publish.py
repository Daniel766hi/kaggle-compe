"""Publish the IMDb SQLite builder kit as a new version of the Kaggle dataset.

    python imdb_kit/publish.py [--counts counts.json]

The dataset holds the builder script and its documentation, not IMDb data: IMDb's datasets are
for personal and non-commercial use and are downloaded from IMDb by whoever runs the script.
--counts adds the row counts measured by the latest test build (a JSON {table: rows, ...}
with a "built_on" date) to the description.
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kaggle_pipeline import kaggle_sync  # noqa: E402

HERE = Path(__file__).resolve().parent
SLUG = "imdb-sqlite-database"
NOTEBOOK = "https://www.kaggle.com/code/danielaijdkx/imdb-in-sqlite-build-and-query-in-minutes"
TITLE = "IMDb SQLite Builder: Full IMDb Data in SQL"
SUBTITLE = "Build a SQLite database of IMDb's official datasets in minutes, legally"


def counts_table(counts):
    if not counts:
        return ("Row counts depend on the day you build (IMDb updates its files daily); the "
                f"[example notebook]({NOTEBOOK}) prints them.")
    lines = [f"Measured in a test build on {counts['built_on']} (IMDb updates its files daily):", "",
             "| Table | Rows |", "|---|---|"]
    lines += [f"| `{t}` | {n:,} |" for t, n in counts.items() if t != "built_on"]
    return "\n".join(lines)


def description(counts):
    return "\n".join([
        "A ready-to-run **builder for a SQLite database of IMDb's official datasets**: titles, ratings, "
        "people, crew, cast, episodes and alternative titles, with clean column names, proper types, "
        "a normalized genre table, indexes and ready-made views. One command, standard-library Python only.",
        "",
        "## Why a builder instead of a database file",
        "",
        "IMDb publishes its datasets for **personal and non-commercial use** under its own terms "
        "(https://developer.imdb.com/non-commercial-datasets/). Re-uploading them under another license "
        "is not allowed, so this dataset contains **the code, not IMDb's data**: the script downloads the "
        "files directly from https://datasets.imdbws.com when you run it, so you always get today's data, "
        "under IMDb's terms.",
        "",
        "## Quick start (in a Kaggle notebook, with Internet turned on)",
        "",
        "```python",
        "import subprocess, sqlite3",
        "subprocess.run(['python', '/kaggle/input/imdb-sqlite-database/build_imdb_sqlite.py',",
        "                '--db', '/kaggle/temp/imdb.sqlite'], check=True)   # core tables, about 10 minutes",
        "con = sqlite3.connect('/kaggle/temp/imdb.sqlite')",
        "con.execute('SELECT * FROM top_rated_movies LIMIT 10').fetchall()",
        "```",
        "",
        "Add `--all` to also load `title_akas` (alternative titles; much larger). The "
        f"[example notebook]({NOTEBOOK}) builds the database and runs example queries.",
        "",
        "## What gets built",
        "",
        "| Table | Source file | Contents |",
        "|---|---|---|",
        "| `title_basics` | title.basics | Movies, series, episodes, shorts: type, titles, year, runtime, genres, plus `decade` |",
        "| `title_genres` | (derived) | One row per title and genre, for easy genre queries |",
        "| `title_ratings` | title.ratings | Average IMDb rating and number of votes |",
        "| `name_basics` | name.basics | People: name, birth and death year, professions, known-for titles |",
        "| `title_crew` | title.crew | Directors and writers per title |",
        "| `title_principals` | title.principals | Main cast and crew per title, with role and characters |",
        "| `title_episode` | title.episode | Episode to series, season and episode number |",
        "| `title_akas` | title.akas | Alternative and international titles (only with `--all`) |",
        "",
        "Views: `top_rated_movies` (IMDb-style weighted rating, 25,000+ votes, top 250), `top_rated_tv` "
        "(10,000+ votes, top 100) and `genre_decade_summary` (movies, average rating and votes per genre "
        "and decade).",
        "",
        "Conventions: snake_case column names (`startYear` becomes `start_year`), IMDb's `\\N` becomes NULL, "
        "years, counts and ratings are stored as numbers, and indexes cover the usual joins.",
        "",
        "## Row counts",
        "",
        counts_table(counts),
        "",
        "## Files",
        "",
        "| File | Description |",
        "|---|---|",
        "| `build_imdb_sqlite.py` | The builder (Python standard library only) |",
        "| `README.md` | This documentation |",
        "",
        "## License and attribution",
        "",
        "- The builder code is released under the MIT license.",
        "- The data it downloads comes from IMDb (https://www.imdb.com), courtesy of IMDb, and is subject "
        "to IMDb's terms for its non-commercial datasets. This project is not affiliated with or endorsed "
        "by IMDb.",
        "",
        "Earlier versions of this dataset described a pre-built 11 GB database that was never uploaded, "
        "and labelled IMDb's data CC0. Both were wrong; this version replaces them with a working builder.",
    ])


def cover(path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(5.6, 2.8), dpi=100)
    fig.patch.set_facecolor("#14161c")
    fig.text(0.5, 0.66, "IMDb  →  SQLite", ha="center", color="#f5c518", fontsize=28, fontweight="bold")
    fig.text(0.5, 0.45, "Build IMDb's official datasets into one SQL database", ha="center", color="#e6e5e0",
             fontsize=11)
    fig.text(0.5, 0.30, "titles · ratings · people · cast · episodes · genres",
             ha="center", color="#9a9a9a", fontsize=10)
    fig.savefig(path, facecolor=fig.get_facecolor())
    plt.close(fig)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--counts")
    args = p.parse_args()
    counts = json.loads(Path(args.counts).read_text()) if args.counts else None
    owner = os.environ.get("KAGGLE_USERNAME") or sys.exit("Set KAGGLE_USERNAME")
    ref = f"{owner}/{SLUG}"
    api = kaggle_sync.get_api()
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        shutil.copy(HERE / "build_imdb_sqlite.py", folder / "build_imdb_sqlite.py")
        desc = description(counts)
        (folder / "README.md").write_text(f"# {TITLE}\n\n{desc}\n")
        cover(folder / "dataset-cover-image.png")
        meta = {
            "title": TITLE, "subtitle": SUBTITLE, "id": ref, "licenses": [{"name": "other"}],
            "keywords": ["movies and tv shows", "sql", "arts and entertainment", "popular culture", "tabular"],
            "description": desc, "expectedUpdateFrequency": "never",
            "userSpecifiedSources": "IMDb non-commercial datasets (https://datasets.imdbws.com), downloaded "
                                    "by the builder at run time under IMDb's terms.",
            "resources": [
                {"path": "build_imdb_sqlite.py", "description": "Builder script (Python standard library only)."},
                {"path": "README.md", "description": "Documentation: tables, views, usage and license."},
            ],
        }
        (folder / "dataset-metadata.json").write_text(json.dumps(meta, indent=2))
        kaggle_sync.publish(api, folder, True, "Replace the missing database with a working builder", False)
        kaggle_sync.wait_until_ready(api, ref)
        # Visibility stays as it is; the license changes from the wrong CC0 to "other" (IMDb's terms).
        meta_path = folder / "dataset-metadata.json"
        kaggle_sync.update_settings(api, folder, ref)
        fixed = json.loads(meta_path.read_text())
        fixed["licenses"] = [{"name": "other"}]
        meta_path.write_text(json.dumps(fixed))
        kaggle_sync._send_settings(api, ref, folder)
        print(f"published https://www.kaggle.com/datasets/{ref}")


if __name__ == "__main__":
    main()
