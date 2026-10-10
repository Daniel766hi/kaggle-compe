"""Building blocks every dataset is described with: tables, columns and the dataset spec.

Table kinds:
- "history":     the source returns the full time series; the file is rebuilt every run.
- "snapshot":    the source only returns the current state; each run appends one dated
                 snapshot to a growing panel (keyed by snapshot_date).
- "incremental": the source has history but is too big to refetch daily; each run fetches
                 new or missing ranges and upserts them by key.
- "derived":     computed from the other tables after they are built (e.g. daily summaries).
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

# Kaggle column types: string, integer, number, boolean, datetime
PANDAS_DTYPES = {
    "string": "string",
    "integer": "Int64",
    "number": "float64",
    "boolean": "boolean",
    "datetime": "datetime64[ns]",
}

KINDS = ("history", "snapshot", "incremental", "derived")


@dataclass(frozen=True)
class Column:
    name: str
    type: str
    description: str


@dataclass(frozen=True)
class Table:
    name: str
    kind: str
    description: str
    columns: list = field(default_factory=list)
    # A fetch that returns fewer rows than this is treated as a source failure.
    min_rows: int = 1
    # Columns that identify one row (used for de-duplication and upserts).
    key: tuple = ()
    fmt: str = ""  # "csv" or "parquet"; default: parquet for snapshots, csv otherwise

    def __post_init__(self):
        assert self.kind in KINDS, self.kind

    @property
    def file_format(self):
        return self.fmt or ("parquet" if self.kind == "snapshot" else "csv")

    @property
    def file_name(self):
        return f"{self.name}.{self.file_format}"

    @property
    def has_latest_file(self):
        return self.kind == "snapshot"

    @property
    def latest_file_name(self):
        return f"{self.name.removesuffix('_snapshots')}_latest.csv"

    @property
    def column_names(self):
        return [c.name for c in self.columns]


@dataclass
class DatasetSpec:
    """Everything that makes one Kaggle dataset: identity, tables and how to fetch them."""

    name: str  # CLI name, e.g. "defi"
    slug: str  # Kaggle URL slug (6-50 chars)
    title: str  # 6-50 chars
    subtitle: str  # 20-80 chars
    license: str
    keywords: list
    tables: list
    sources: str  # shown as "Source/Provenance" on Kaggle
    # (session, snapshot_date) -> {table name: fetch(previous_df_or_None) -> DataFrame}
    make_fetchers: Callable
    # (snapshot_date, tables_written) -> markdown description
    describe: Callable
    # {table name: DataFrame} of built tables -> {derived table name: DataFrame}
    derive: Optional[Callable] = None
    cover: Optional[Path] = None
    update_frequency: str = "daily"

    def table(self, name):
        return next(t for t in self.tables if t.name == name)

    @property
    def base_tables(self):
        return [t for t in self.tables if t.kind != "derived"]

    @property
    def derived_tables(self):
        return [t for t in self.tables if t.kind == "derived"]


def files_markdown(tables_written):
    """The '## Files' table every dataset description includes."""
    lines = ["| File | Description |", "|---|---|"]
    for table in tables_written:
        lines.append(f"| `{table.file_name}` | {table.description} |")
        if table.has_latest_file:
            lines.append(f"| `{table.latest_file_name}` | Most recent day of `{table.file_name}`, as CSV. |")
    return "\n".join(lines)
