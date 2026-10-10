"""DataFrame helpers shared by all datasets."""

import pandas as pd

from .schema import PANDAS_DTYPES


def conform(df, table):
    """Return df with exactly the table's columns, in order, with the declared dtypes,
    de-duplicated on the table key (last row wins) and sorted by it."""
    df = df.copy()
    for col in table.columns:
        if col.name not in df.columns:
            df[col.name] = pd.NA
        series = df[col.name]
        if col.type == "datetime":
            df[col.name] = pd.to_datetime(series, errors="coerce")
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
