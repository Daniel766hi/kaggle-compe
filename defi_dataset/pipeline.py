"""Build one dataset version: fetch every source, merge with the previous version, write files.

Each table is built independently. If a source fails, the previous version of that
table is carried forward unchanged, so one broken endpoint never deletes data.
"""

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import sources, storage, transform
from .schema import TABLES_BY_NAME

log = logging.getLogger(__name__)


@dataclass
class BuildReport:
    updated: dict = field(default_factory=dict)  # table name -> rows fetched today
    carried_forward: list = field(default_factory=list)
    failed: dict = field(default_factory=dict)  # table name -> error message
    tables_written: list = field(default_factory=list)

    def version_notes(self, snapshot_date):
        parts = [f"Daily update {snapshot_date:%Y-%m-%d} UTC"]
        if self.carried_forward:
            parts.append("unchanged (source error): " + ", ".join(sorted(self.carried_forward)))
        return "; ".join(parts)


def _fetchers(session, snapshot_date):
    """Map table name -> zero-arg function that returns today's DataFrame."""
    cache = {}

    def chains():
        if "chains" not in cache:
            cache["chains"] = transform.chains_snapshot(sources.fetch_chains(session), snapshot_date)
        return cache["chains"]

    return {
        "defi_tvl_history": lambda: transform.defi_tvl_history(sources.fetch_defi_tvl_history(session)),
        "chain_tvl_history": lambda: transform.chain_tvl_history(
            sources.fetch_chain_tvl_histories(session, transform.top_chains(chains()))
        ),
        "stablecoin_supply_history": lambda: transform.stablecoin_supply_history(
            sources.fetch_stablecoin_supply_history(session)
        ),
        "dex_fees_history": lambda: transform.dex_fees_history(
            sources.fetch_dex_overview(session), sources.fetch_fees_overview(session)
        ),
        "protocols_snapshots": lambda: transform.protocols_snapshot(sources.fetch_protocols(session), snapshot_date),
        "chains_snapshots": chains,
        "stablecoins_snapshots": lambda: transform.stablecoins_snapshot(
            sources.fetch_stablecoins(session), snapshot_date
        ),
        "yield_pools_snapshots": lambda: transform.yield_pools_snapshot(
            sources.fetch_yield_pools(session), snapshot_date
        ),
    }


def build(out_dir, previous_dir, snapshot_date, dataset_ref, fetchers=None):
    """Write all table files plus dataset-metadata.json into out_dir.

    previous_dir holds the files of the current Kaggle version (or None on first run).
    fetchers can be injected for testing; by default it calls the live API.
    """
    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    if fetchers is None:
        fetchers = _fetchers(sources.make_session(), snapshot_date)

    report = BuildReport()
    for name, fetch in fetchers.items():
        table = TABLES_BY_NAME[name]
        previous = storage.read_table(table, previous_dir)
        try:
            today = fetch()
            if len(today) < table.min_rows:
                raise ValueError(f"only {len(today)} rows, expected at least {table.min_rows}")
            new = storage.merge_snapshot(previous, today, table) if table.kind == "snapshot" else today
            storage.check_not_shrinking(previous, new, table)
            report.updated[name] = len(today)
            log.info("%-28s ok: %d rows today, %d rows total", name, len(today), len(new))
        except Exception as exc:  # noqa: BLE001 - one bad source must not stop the others
            report.failed[name] = f"{type(exc).__name__}: {exc}"
            log.warning("%-28s FAILED: %s", name, report.failed[name])
            if previous is None:
                continue
            new = previous
            report.carried_forward.append(name)
        storage.write_table(new, table, out_dir)
        report.tables_written.append(table)

    if not report.updated:
        raise RuntimeError(f"Every source failed, nothing to publish: {report.failed}")

    report.tables_written = storage.ordered(report.tables_written)
    storage.write_metadata(out_dir, report.tables_written, snapshot_date, dataset_ref)
    return report
