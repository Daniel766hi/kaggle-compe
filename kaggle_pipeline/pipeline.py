"""Build one dataset version: fetch every source, merge with the previous version, write files.

Each table is built independently. If a source fails, the previous version of that
table is carried forward unchanged, so one broken endpoint never deletes data.
"""

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import storage
from .frames import conform
from .http import make_session

log = logging.getLogger(__name__)


@dataclass
class BuildReport:
    updated: dict = field(default_factory=dict)  # table name -> rows fetched this run
    carried_forward: list = field(default_factory=list)
    failed: dict = field(default_factory=dict)  # table name -> error message
    tables_written: list = field(default_factory=list)

    frequency: str = "daily"

    def version_notes(self, snapshot_date):
        parts = [f"{self.frequency.capitalize()} update {snapshot_date:%Y-%m-%d} UTC"]
        if self.carried_forward:
            parts.append("unchanged (source error): " + ", ".join(sorted(self.carried_forward)))
        return "; ".join(parts)


def build(spec, out_dir, previous_dir, snapshot_date, dataset_ref, fetchers=None):
    """Write all table files plus dataset-metadata.json into out_dir.

    previous_dir holds the files of the current Kaggle version (or None on first run).
    fetchers can be injected for testing; by default they call the live sources.
    """
    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    if fetchers is None:
        fetchers = spec.make_fetchers(make_session(), snapshot_date)

    report = BuildReport(frequency=spec.update_frequency)
    frames = {}
    for table in spec.base_tables:
        previous = storage.read_table(table, previous_dir)
        try:
            fetched = conform(fetchers[table.name](previous), table)
            if len(fetched) < table.min_rows:
                raise ValueError(f"only {len(fetched)} rows, expected at least {table.min_rows}")
            new = storage.merge(table, previous, fetched)
            storage.check_not_shrinking(previous, new, table)
            report.updated[table.name] = len(fetched)
            log.info("%-30s ok: %d rows fetched, %d rows total", table.name, len(fetched), len(new))
        except Exception as exc:  # noqa: BLE001 - one bad source must not stop the others
            report.failed[table.name] = f"{type(exc).__name__}: {exc}"
            log.warning("%-30s FAILED: %s", table.name, report.failed[table.name])
            if previous is None:
                continue
            new = previous
            report.carried_forward.append(table.name)
        frames[table.name] = new
        storage.write_table(new, table, out_dir)
        report.tables_written.append(table)

    if not report.updated:
        raise RuntimeError(f"Every source failed, nothing to publish: {report.failed}")

    if spec.derived_tables:
        try:
            derived = spec.derive(frames)
            for table in spec.derived_tables:
                df = conform(derived[table.name], table)
                storage.write_table(df, table, out_dir)
                report.tables_written.append(table)
                log.info("%-30s derived: %d rows", table.name, len(df))
        except Exception as exc:  # noqa: BLE001
            report.failed["derived"] = f"{type(exc).__name__}: {exc}"
            log.warning("derived tables FAILED: %s", report.failed["derived"])
            written = {t.name for t in report.tables_written}
            for table in spec.derived_tables:
                previous = storage.read_table(table, previous_dir)
                if table.name not in written and previous is not None:
                    storage.write_table(previous, table, out_dir)
                    report.tables_written.append(table)
                    report.carried_forward.append(table.name)

    order = {t.name: i for i, t in enumerate(spec.tables)}
    report.tables_written.sort(key=lambda t: order[t.name])
    storage.write_metadata(spec, out_dir, report.tables_written, snapshot_date, dataset_ref, frames)
    storage.copy_cover_image(spec, out_dir)
    return report
