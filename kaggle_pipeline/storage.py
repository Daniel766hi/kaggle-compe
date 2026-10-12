"""Read previous files, merge in new data, write the upload folder and its metadata."""

import json
import shutil
from pathlib import Path

import pandas as pd

from .frames import conform

# Kaggle's own names for column types (it calls floats "numeric").
KAGGLE_COLUMN_TYPES = {"number": "numeric"}


def read_table(table, folder):
    """Read a table file from a previous dataset version, or return None if absent."""
    if folder is None:
        return None
    path = Path(folder) / table.file_name
    if not path.exists():
        return None
    if table.file_format == "csv":
        df = pd.read_csv(path, parse_dates=[c.name for c in table.columns if c.type == "datetime"])
    else:
        df = pd.read_parquet(path)
    return conform(df, table)


def merge(table, previous, fetched):
    """Combine the previous version of a table with what was fetched this run."""
    if table.kind in ("history", "derived") or previous is None or previous.empty:
        return fetched
    if fetched is None or fetched.empty:
        return previous
    if table.kind == "snapshot":
        # Re-running on the same day replaces that day's snapshot.
        kept = previous[~previous["snapshot_date"].isin(fetched["snapshot_date"].unique())]
        return conform(pd.concat([kept, fetched], ignore_index=True), table)
    # incremental: upsert by key, fetched rows win
    return conform(pd.concat([previous, fetched], ignore_index=True), table)


def check_not_shrinking(previous, new, table):
    """Refuse to publish a table that lost history compared with the previous version."""
    if previous is None or previous.empty or table.kind == "derived":
        return
    dates = [c for c in table.key if any(col.name == c and col.type == "datetime" for col in table.columns)]
    if table.kind == "snapshot":
        before, after = previous["snapshot_date"].nunique(), new["snapshot_date"].nunique()
        what = "snapshot days"
    elif table.kind == "history" and dates:
        # Full histories are compared by days covered, not rows: a member can legitimately
        # leave (e.g. a chain dropping out of the top 25) without any history being lost.
        before, after = previous[dates[0]].nunique(), new[dates[0]].nunique()
        what = "days"
    else:
        before, after = len(previous), len(new)
        what = "rows"
    if after < before * (1 - table.max_shrink):
        raise ValueError(f"{table.name}: would shrink from {before} to {after} {what}")


def write_table(df, table, out_dir):
    out_dir = Path(out_dir)
    if table.file_format == "csv":
        df.to_csv(out_dir / table.file_name, index=False)
    else:
        df.to_parquet(out_dir / table.file_name, index=False)
    if table.has_latest_file:
        latest = df[df["snapshot_date"] == df["snapshot_date"].max()]
        latest.to_csv(out_dir / table.latest_file_name, index=False)


def _resource(path, description, table):
    return {
        "path": path,
        "description": description,
        "schema": {
            "fields": [
                {"name": c.name, "description": c.description, "type": KAGGLE_COLUMN_TYPES.get(c.type, c.type)}
                for c in table.columns
            ]
        },
    }


def write_metadata(spec, out_dir, tables_written, snapshot_date, dataset_ref):
    resources = []
    for table in tables_written:
        resources.append(_resource(table.file_name, table.description, table))
        if table.has_latest_file:
            resources.append(_resource(table.latest_file_name, f"Most recent day of {table.file_name}.", table))
    metadata = {
        "title": spec.title,
        "subtitle": spec.subtitle,
        "id": dataset_ref,
        "licenses": [{"name": spec.license}],
        "keywords": spec.keywords,
        "description": spec.describe(snapshot_date, tables_written),
        "expectedUpdateFrequency": spec.update_frequency,
        "userSpecifiedSources": spec.sources,
        "resources": resources,
    }
    with open(Path(out_dir) / "dataset-metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)


def copy_cover_image(spec, out_dir):
    """Kaggle picks up dataset-cover-image.png next to dataset-metadata.json."""
    if spec.cover and Path(spec.cover).exists():
        shutil.copyfile(spec.cover, Path(out_dir) / "dataset-cover-image.png")
