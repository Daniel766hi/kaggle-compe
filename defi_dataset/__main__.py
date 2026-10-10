"""Run the daily update.

    python -m defi_dataset              # scrape, merge with Kaggle's current version, upload
    python -m defi_dataset --dry-run    # scrape and write files to ./build only
"""

import argparse
import logging
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import config, kaggle_sync, pipeline


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="build files locally, don't touch Kaggle")
    parser.add_argument("--out-dir", default="build", help="where to write the dataset files")
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

    snapshot_date = pd.Timestamp(datetime.now(timezone.utc).date())

    if args.dry_run:
        ref = f"{config.KAGGLE_OWNER or 'your-kaggle-username'}/{config.DATASET_SLUG}"
        report = pipeline.build(args.out_dir, args.previous_dir, snapshot_date, ref)
        _summarize(report, snapshot_date)
        return 0

    ref = config.dataset_ref()
    api = kaggle_sync.get_api()
    exists = kaggle_sync.dataset_exists(api, ref)
    with tempfile.TemporaryDirectory() as tmp:
        previous_dir = None
        if exists:
            previous_dir = Path(tmp)
            kaggle_sync.download_current(api, ref, previous_dir)
        report = pipeline.build(args.out_dir, previous_dir, snapshot_date, ref)
    _summarize(report, snapshot_date)
    kaggle_sync.publish(api, args.out_dir, exists, report.version_notes(snapshot_date), args.public)
    # Published, but exit non-zero so a failing source shows up as a red run (and an email).
    return 1 if report.failed else 0


def _summarize(report, snapshot_date):
    logging.info("Version notes: %s", report.version_notes(snapshot_date))
    for name, err in report.failed.items():
        logging.warning("Source failed for %s: %s", name, err)


if __name__ == "__main__":
    sys.exit(main())
