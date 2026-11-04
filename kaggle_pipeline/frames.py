"""DataFrame helpers shared by all datasets."""

import pandas as pd

from .schema import PANDAS_DTYPES

# Nanosecond timestamps (the declared datetime dtype) only cover these years. pandas 3 parses dates
# such as Wikidata's "0001-01-01" placeholder at a coarser unit, so they must be dropped before the cast.
NS_FIRST, NS_LAST = pd.Timestamp("1677-09-22"), pd.Timestamp("2262-04-11")


def conform(df, table):
    """Return df with exactly the table's columns, in order, with the declared dtypes,
    de-duplicated on the table key (last row wins) and sorted by it."""
    df = df.copy()
    for col in table.columns:
        if col.name not in df.columns:
            df[col.name] = pd.NA
        series = df[col.name]
        if col.type == "datetime":
            dates = pd.to_datetime(series, errors="coerce")
            df[col.name] = dates.where((dates >= NS_FIRST) & (dates <= NS_LAST))
        elif col.type in ("number", "integer"):
            df[col.name] = pd.to_numeric(series, errors="coerce")
            if col.type == "integer":
                df[col.name] = df[col.name].round()
        elif col.type == "boolean":
            df[col.name] = series.map(lambda v: v if isinstance(v, bool) else pd.NA)
        df[col.name] = df[col.name].astype(PANDAS_DTYPES[col.type])
    df = df[table.column_names]
    if table.key:
        df = df.dropna(subset=list(table.key)).drop_duplicates(subset=list(table.key), keep="last")
        df = df.sort_values(list(table.key)).reset_index(drop=True)
    return df


def unix_to_date(values):
    secs = pd.to_numeric(pd.Series(values), errors="coerce")
    return pd.to_datetime(secs, unit="s", utc=True).dt.tz_localize(None).dt.normalize()


def unix_to_datetime(values):
    secs = pd.to_numeric(pd.Series(values), errors="coerce")
    return pd.to_datetime(secs, unit="s", utc=True).dt.tz_localize(None)
