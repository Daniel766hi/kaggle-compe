"""Run the daily update for one dataset.

    python -m kaggle_pipeline defi              # scrape, merge with Kaggle's current version, upload
    python -m kaggle_pipeline defi --dry-run    # scrape and write files to ./build/defi only
"""

import argparse
import logging
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import kaggle_sync, pipeline
from .datasets import DATASETS


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dataset", choices=sorted(DATASETS))
    parser.add_argument("--dry-run", action="store_true", help="build files locally, don't touch Kaggle")
    parser.add_argument("--out-dir", help="where to write the dataset files (default: build/<dataset>)")
    parser.add_argument(
        "--previous-dir",
        help="folder with the previous version's files (dry run only; default: start fresh)",
    )
    parser.add_argument(
        "--public",
        action="store_true",
        default=os.environ.get("KAGGLE_DATASET_PUBLIC", "").lower() == "true",
        help="when creating the dataset for the first time, make it public (default: private)",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    spec = DATASETS[args.dataset]
    out_dir = args.out_dir or f"build/{spec.name}"
    snapshot_date = pd.Timestamp(datetime.now(timezone.utc).date())
    owner = os.environ.get("KAGGLE_USERNAME") or ""

    scheduled = os.environ.get("GITHUB_EVENT_NAME") == "schedule"
    if scheduled and spec.run_weekday is not None and snapshot_date.weekday() != spec.run_weekday:
        logging.info("%s updates weekly; skipping today's scheduled run", spec.name)
        return 0

    if args.dry_run:
        ref = f"{owner or 'your-kaggle-username'}/{spec.slug}"
        report = pipeline.build(spec, out_dir, args.previous_dir, snapshot_date, ref)
        _summarize(report, snapshot_date)
        _describe_files(report, out_dir)
        return 1 if report.failed else 0

    if not owner:
        raise SystemExit("Set KAGGLE_USERNAME to your Kaggle username.")
    ref = f"{owner}/{spec.slug}"
    api = kaggle_sync.get_api()
    exists = kaggle_sync.dataset_exists(api, ref)
    with tempfile.TemporaryDirectory() as tmp:
        previous_dir = None
        if exists:
            previous_dir = Path(tmp)
            kaggle_sync.download_current(api, ref, previous_dir)
        report = pipeline.build(spec, out_dir, previous_dir, snapshot_date, ref)
    _summarize(report, snapshot_date)
    kaggle_sync.publish(api, out_dir, exists, report.version_notes(snapshot_date), args.public)
    kaggle_sync.wait_until_ready(api, ref)
    kaggle_sync.update_settings(api, out_dir, ref)
    # Published, but exit non-zero so a failing source shows up as a red run (and an email).
    return 1 if report.failed else 0


def _describe_files(report, out_dir):
    """Log size and date range of every file, to check a dry run at a glance."""
    for table in report.tables_written:
        path = Path(out_dir) / table.file_name
        df = pd.read_csv(path) if table.file_format == "csv" else pd.read_parquet(path)
        dates = [c.name for c in table.columns if c.type == "datetime"][:1]
        span = f"{pd.to_datetime(df[dates[0]]).min()} -> {pd.to_datetime(df[dates[0]]).max()}" if dates else ""
        logging.info("%-32s %9d rows  %s", table.file_name, len(df), span)
        filled = (df.notna().mean() * 100).round(1)
        partial = {c: v for c, v in filled.items() if v < 100}
        if partial:
            logging.info("    columns not always filled (%% of rows): %s", partial)


def _summarize(report, snapshot_date):
    logging.info("Version notes: %s", report.version_notes(snapshot_date))
    for name, err in report.failed.items():
        logging.warning("Source failed for %s: %s", name, err)


if __name__ == "__main__":
    sys.exit(main())
