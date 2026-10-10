"""Read previous files, merge in today's data, write the upload folder."""

import json
from pathlib import Path

import pandas as pd

from . import config
from .schema import TABLES
from .transform import conform


def read_table(table, folder):
    """Read a table file from a previous dataset version, or return None if absent."""
    if folder is None:
        return None
    path = Path(folder) / table.file_name
    if not path.exists():
        return None
    if table.kind == "history":
        df = pd.read_csv(path, parse_dates=[c.name for c in table.columns if c.type == "datetime"])
    else:
        df = pd.read_parquet(path)
    return conform(df, table)


def merge_snapshot(previous, today, table):
    """Append today's snapshot to the panel. Re-running on the same day replaces that day."""
    if previous is None or previous.empty:
        return today
    if today is None or today.empty:
        return previous
    dates = today["snapshot_date"].unique()
    kept = previous[~previous["snapshot_date"].isin(dates)]
    return conform(pd.concat([kept, today], ignore_index=True), table)


def check_not_shrinking(previous, new, table):
    """Refuse to publish a table that lost history compared with the previous version."""
    if previous is None or previous.empty:
        return
    if table.kind == "snapshot":
        before, after = previous["snapshot_date"].nunique(), new["snapshot_date"].nunique()
        what = "snapshot days"
    else:
        before, after = len(previous), len(new)
        what = "rows"
    if after < before:
        raise ValueError(f"{table.name}: would shrink from {before} to {after} {what}")


def write_table(df, table, out_dir):
    out_dir = Path(out_dir)
    if table.kind == "history":
        df.to_csv(out_dir / table.file_name, index=False, date_format="%Y-%m-%d")
        return [table.file_name]
    df.to_parquet(out_dir / table.file_name, index=False)
    latest = df[df["snapshot_date"] == df["snapshot_date"].max()]
    latest.to_csv(out_dir / table.latest_file_name, index=False, date_format="%Y-%m-%d")
    return [table.file_name, table.latest_file_name]


def _resource(path, description, table):
    return {
        "path": path,
        "description": description,
        "schema": {
            "fields": [{"name": c.name, "description": c.description, "type": c.type} for c in table.columns]
        },
    }


def build_description(tables_written, snapshot_date):
    lines = [
        "Daily-updated data on decentralized finance (DeFi): total value locked (TVL), "
        "blockchains, stablecoins, DEX trading volume, protocol fees and yield pools.",
        "",
        "## Why this dataset",
        "",
        "The API's list endpoints only return the *current* state of every protocol, stablecoin "
        "and yield pool. This dataset saves that state every day, so the `*_snapshots.parquet` "
        "files grow into one ready-to-use, day-by-day panel instead of thousands of separate API "
        "calls. Use it to study protocol growth, stablecoin market share, yield changes, or "
        "category trends over time.",
        "",
        "## Files",
        "",
        "| File | Description |",
        "|---|---|",
    ]
    for table in tables_written:
        lines.append(f"| `{table.file_name}` | {table.description} |")
        if table.kind == "snapshot":
            lines.append(f"| `{table.latest_file_name}` | Most recent day of `{table.file_name}`, as CSV. |")
    lines += [
        "",
        "## Updates",
        "",
        f"Refreshed daily by an automated pipeline. Last update: {snapshot_date:%Y-%m-%d} (UTC). "
        "Snapshot panels start on the first day the pipeline ran.",
        "",
        "## Source and attribution",
        "",
        "All data comes from the free public [DefiLlama API](https://defillama.com/docs/api). "
        "Please credit **DefiLlama** when you use this data. Values are as reported by DefiLlama "
        "and can be revised by them later; history files are re-downloaded in full each day.",
        "",
        "## Notes",
        "",
        "- All amounts are in USD unless stated otherwise. Dates are UTC.",
        f"- Yield pools are limited to pools with at least ${config.MIN_POOL_TVL_USD:,.0f} TVL.",
        f"- `chain_tvl_history` covers the {config.TOP_CHAINS_FOR_HISTORY} largest chains by current TVL.",
        "- `protocols_snapshots` includes CEX entries (category `CEX`); filter them out for pure DeFi.",
    ]
    return "\n".join(lines)


def write_metadata(out_dir, tables_written, snapshot_date, dataset_ref):
    resources = []
    for table in tables_written:
        resources.append(_resource(table.file_name, table.description, table))
        if table.kind == "snapshot":
            resources.append(_resource(
                table.latest_file_name, f"Most recent day of {table.file_name}.", table
            ))
    metadata = {
        "title": config.DATASET_TITLE,
        "subtitle": config.DATASET_SUBTITLE,
        "id": dataset_ref,
        "licenses": [{"name": config.DATASET_LICENSE}],
        "keywords": config.DATASET_KEYWORDS,
        "description": build_description(tables_written, snapshot_date),
        "resources": resources,
    }
    with open(Path(out_dir) / "dataset-metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)


def ordered(tables):
    """Keep tables in schema order so the file list is stable between versions."""
    names = {t.name for t in tables}
    return [t for t in TABLES if t.name in names]
