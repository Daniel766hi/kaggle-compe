"""Turn raw DefiLlama JSON into tidy DataFrames that match schema.TABLES.

Every function is pure (no network), so it can be tested against fixtures.
The API has no formal schema, so all field access is defensive.
"""

import pandas as pd

from . import config
from .schema import PANDAS_DTYPES, TABLES_BY_NAME


def _unix_to_date(values):
    secs = pd.to_numeric(pd.Series(values), errors="coerce")
    return pd.to_datetime(secs, unit="s", utc=True).dt.tz_localize(None).dt.normalize()


def _unix_to_datetime(values):
    secs = pd.to_numeric(pd.Series(values), errors="coerce")
    return pd.to_datetime(secs, unit="s", utc=True).dt.tz_localize(None)


def _join(items):
    return "|".join(str(i) for i in items) if isinstance(items, list) else None


def _str_or_none(value):
    return None if value is None else str(value)


def conform(df, table):
    """Return df with exactly the table's columns, in order, with the declared dtypes."""
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


# ---------- history tables ----------

def defi_tvl_history(raw):
    df = pd.DataFrame({
        "date": _unix_to_date([r.get("date") for r in raw]),
        "tvl_usd": [r.get("tvl") for r in raw],
    })
    return conform(df, TABLES_BY_NAME["defi_tvl_history"])


def chain_tvl_history(raw_by_chain):
    frames = []
    for chain, rows in raw_by_chain.items():
        frames.append(pd.DataFrame({
            "date": _unix_to_date([r.get("date") for r in rows]),
            "chain": chain,
            "tvl_usd": [r.get("tvl") for r in rows],
        }))
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return conform(df, TABLES_BY_NAME["chain_tvl_history"])


def stablecoin_supply_history(raw):
    def total_usd(row):
        values = (row.get("totalCirculatingUSD") or {}).values()
        numbers = [v for v in values if isinstance(v, (int, float))]
        return sum(numbers) if numbers else None

    df = pd.DataFrame({
        "date": _unix_to_date([r.get("date") for r in raw]),
        "total_circulating_usd": [total_usd(r) for r in raw],
    })
    return conform(df, TABLES_BY_NAME["stablecoin_supply_history"])


def _chart_to_frame(raw, value_name):
    points = [p for p in (raw or {}).get("totalDataChart") or [] if isinstance(p, list) and len(p) == 2]
    return pd.DataFrame({
        "date": _unix_to_date([p[0] for p in points]),
        value_name: [p[1] for p in points],
    })


def dex_fees_history(dex_raw, fees_raw):
    dex = _chart_to_frame(dex_raw, "dex_volume_usd")
    fees = _chart_to_frame(fees_raw, "fees_usd")
    df = dex.merge(fees, on="date", how="outer")
    return conform(df, TABLES_BY_NAME["dex_fees_history"])


# ---------- snapshot tables ----------

def protocols_snapshot(raw, snapshot_date):
    rows = []
    for p in raw:
        if p.get("tvl") is None:
            continue
        chains = p.get("chains") or []
        rows.append({
            "protocol_id": _str_or_none(p.get("id")),
            "name": p.get("name"),
            "slug": p.get("slug"),
            "symbol": None if p.get("symbol") in (None, "-") else p.get("symbol"),
            "category": p.get("category"),
            "primary_chain": p.get("chain"),
            "chains": _join(chains),
            "n_chains": len(chains),
            "tvl_usd": p.get("tvl"),
            "change_1h_pct": p.get("change_1h"),
            "change_1d_pct": p.get("change_1d"),
            "change_7d_pct": p.get("change_7d"),
            "mcap_usd": p.get("mcap"),
            "parent_protocol": p.get("parentProtocol"),
            "listed_at": p.get("listedAt"),
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df["listed_at"] = _unix_to_datetime(df["listed_at"]).values
    df["snapshot_date"] = pd.Timestamp(snapshot_date)
    return conform(df, TABLES_BY_NAME["protocols_snapshots"])


def chains_snapshot(raw, snapshot_date):
    df = pd.DataFrame([{
        "chain": c.get("name"),
        "tvl_usd": c.get("tvl"),
        "token_symbol": c.get("tokenSymbol"),
        "chain_id": _str_or_none(c.get("chainId")),
    } for c in raw])
    df["snapshot_date"] = pd.Timestamp(snapshot_date)
    return conform(df, TABLES_BY_NAME["chains_snapshots"])


def stablecoins_snapshot(raw, snapshot_date):
    def amount(d, peg_type):
        return (d or {}).get(peg_type) if isinstance(d, dict) else None

    rows = []
    for s in (raw or {}).get("peggedAssets") or []:
        peg = s.get("pegType")
        rows.append({
            "stablecoin_id": _str_or_none(s.get("id")),
            "name": s.get("name"),
            "symbol": s.get("symbol"),
            "peg_type": peg,
            "peg_mechanism": s.get("pegMechanism"),
            "circulating": amount(s.get("circulating"), peg),
            "circulating_prev_day": amount(s.get("circulatingPrevDay"), peg),
            "circulating_prev_week": amount(s.get("circulatingPrevWeek"), peg),
            "circulating_prev_month": amount(s.get("circulatingPrevMonth"), peg),
            "price": s.get("price"),
            "n_chains": len(s.get("chains") or []),
        })
    df = pd.DataFrame(rows)
    df["snapshot_date"] = pd.Timestamp(snapshot_date)
    return conform(df, TABLES_BY_NAME["stablecoins_snapshots"])


def yield_pools_snapshot(raw, snapshot_date, min_tvl_usd=config.MIN_POOL_TVL_USD):
    rows = []
    for p in (raw or {}).get("data") or []:
        tvl = p.get("tvlUsd")
        if not isinstance(tvl, (int, float)) or tvl < min_tvl_usd:
            continue
        rows.append({
            "pool_id": p.get("pool"),
            "chain": p.get("chain"),
            "project": p.get("project"),
            "symbol": p.get("symbol"),
            "pool_meta": p.get("poolMeta"),
            "tvl_usd": tvl,
            "apy": p.get("apy"),
            "apy_base": p.get("apyBase"),
            "apy_reward": p.get("apyReward"),
            "apy_mean_30d": p.get("apyMean30d"),
            "stablecoin": p.get("stablecoin"),
            "il_risk": p.get("ilRisk"),
            "exposure": p.get("exposure"),
            "volume_usd_1d": p.get("volumeUsd1d"),
        })
    df = pd.DataFrame(rows)
    df["snapshot_date"] = pd.Timestamp(snapshot_date)
    return conform(df, TABLES_BY_NAME["yield_pools_snapshots"])


def top_chains(chains_df, n=config.TOP_CHAINS_FOR_HISTORY):
    return chains_df.nlargest(n, "tvl_usd")["chain"].tolist()
