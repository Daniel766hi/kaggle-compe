"""Central bank policy rates: daily and monthly policy interest rates for 40+ central banks (BIS).

Source: Bank for International Settlements (BIS), central bank policy rates (dataflow WS_CBPOL), bulk download from
https://data.bis.org. BIS statistics may be used provided the BIS is cited as the source; they must not be
presented as investment advice or as endorsed by the BIS. The BIS notes structural breaks for some countries (a new
instrument becoming the policy rate); those notes are kept in the countries table.
"""

import io
import logging
import re
import zipfile
from pathlib import Path

import pandas as pd

from ..http import make_session as base_session
from ..schema import Column, DatasetSpec, Table, files_markdown

log = logging.getLogger(__name__)

ASSETS = Path(__file__).resolve().parents[2] / "assets"
BULK = "https://data.bis.org/static/bulk/WS_CBPOL_csv_flat.zip"
COLS = {"FREQ:Frequency": "freq", "REF_AREA:Reference area": "area", "TIME_PERIOD:Time period or range": "period",
        "OBS_VALUE:Observation Value": "value", "TITLE:Title": "title",
        "SUPP_INFO_BREAKS:Supplemental information and breaks": "breaks", "OBS_STATUS:Observation Status": "status"}

DAILY = Table(
    name="policy_rates_daily",
    kind="history",
    description="Per central bank and day: the policy rate in force (% per year). Daily series start in different years per country.",
    key=("country_code", "date"),
    fmt="parquet",  # several hundred thousand rows
    min_rows=200_000,
    max_shrink=0.01,
    columns=[
        Column("date", "datetime", "Day"),
        Column("country_code", "string", "BIS area code: ISO alpha-2 (e.g. ID), or XM for the euro area"),
        Column("country", "string", "Country or currency area"),
        Column("rate_pct", "number", "Policy rate in force that day (% per year)"),
    ],
)

MONTHLY = Table(
    name="policy_rates_monthly",
    kind="history",
    description="Per central bank and month: the policy rate (% per year), from the 1940s for some countries.",
    key=("country_code", "month"),
    min_rows=10_000,
    max_shrink=0.01,
    columns=[
        Column("month", "datetime", "First day of the month"),
        Column("country_code", "string", "BIS area code"),
        Column("country", "string", "Country or currency area"),
        Column("rate_pct", "number", "Policy rate (% per year), end of month as published by the BIS"),
    ],
)

COUNTRIES = Table(
    name="countries",
    kind="history",
    description="One row per central bank: coverage of the monthly and daily series and the BIS note on structural breaks.",
    key=("country_code",),
    min_rows=30,
    columns=[
        Column("country_code", "string", "BIS area code"),
        Column("country", "string", "Country or currency area"),
        Column("first_month", "datetime", "First month with a value"),
        Column("first_day", "datetime", "First day of daily data"),
        Column("breaks_note", "string", "BIS note on breaks in the series (e.g. a change of policy instrument)"),
    ],
)

CHANGES = Table(
    name="rate_changes",
    kind="derived",
    description="One row per policy rate move, from the daily data: date, old and new rate, change in basis points and direction.",
    key=("country_code", "date"),
    min_rows=0,
    columns=[
        Column("date", "datetime", "Day the new rate took effect"),
        Column("country_code", "string", "BIS area code"),
        Column("country", "string", "Country or currency area"),
        Column("old_rate_pct", "number", "Rate before (%)"),
        Column("new_rate_pct", "number", "Rate after (%)"),
        Column("change_bp", "number", "Change in basis points (100 bp = 1 percentage point)"),
        Column("direction", "string", "hike or cut"),
        Column("possible_break", "boolean", "Falls on a day or month the BIS break note mentions; read the note before calling it a policy move"),
    ],
)

LATEST = Table(
    name="latest",
    kind="derived",
    description="One row per central bank: current rate, last move, change over 12 months and the 2022-23 tightening peak.",
    key=("country_code",),
    min_rows=0,
    columns=[
        Column("country_code", "string", "BIS area code"),
        Column("country", "string", "Country or currency area"),
        Column("date", "datetime", "Latest day with data"),
        Column("rate_pct", "number", "Rate on that day (%)"),
        Column("change_12m_bp", "number", "Change over the last 12 months (basis points)"),
        Column("last_move_date", "datetime", "Date of the last change"),
        Column("last_move_bp", "number", "Size of the last change (basis points)"),
        Column("peak_since_2022_pct", "number", "Highest rate since 1 January 2022 (%)"),
        Column("from_peak_bp", "number", "Current rate minus that peak (basis points)"),
    ],
)

TABLES = [DAILY, MONTHLY, COUNTRIES, CHANGES, LATEST]

# ---------- download and parsing ----------


def make_session():
    return base_session()


def download(session):
    resp = session.get(BULK, timeout=600)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        name = next(n for n in z.namelist() if n.endswith(".csv"))
        with z.open(name) as f:
            raw = pd.read_csv(f, usecols=list(COLS), dtype=str).rename(columns=COLS)
    log.info("BIS WS_CBPOL: %d rows", len(raw))
    return raw


def split_code(series):
    """'ID: Indonesia' -> ('ID', 'Indonesia')."""
    parts = series.str.split(": ", n=1, expand=True)
    return parts[0].str.strip(), parts[1].str.strip()


def tidy(raw):
    raw = raw[raw["status"].fillna("").str.startswith("A")].copy()  # normal values; M = data cannot exist
    raw["country_code"], raw["country"] = split_code(raw["area"])
    raw["rate_pct"] = pd.to_numeric(raw["value"], errors="coerce")
    raw = raw.dropna(subset=["rate_pct"])
    daily = raw[raw["freq"].str.startswith("D")]
    monthly = raw[raw["freq"].str.startswith("M")]
    d = pd.DataFrame({"date": pd.to_datetime(daily["period"]), "country_code": daily["country_code"],
                      "country": daily["country"], "rate_pct": daily["rate_pct"]})
    m = pd.DataFrame({"month": pd.to_datetime(monthly["period"]).dt.to_period("M").dt.to_timestamp(),
                      "country_code": monthly["country_code"], "country": monthly["country"], "rate_pct": monthly["rate_pct"]})
    d = d.drop_duplicates(["country_code", "date"]).sort_values(["country_code", "date"]).reset_index(drop=True)
    m = m.drop_duplicates(["country_code", "month"]).sort_values(["country_code", "month"]).reset_index(drop=True)
    meta = raw.groupby("country_code").agg(country=("country", "first"),
                                           breaks_note=("breaks", lambda s: next((x for x in s if isinstance(x, str) and x.strip()), None)))
    meta["first_month"] = m.groupby("country_code")["month"].min()
    meta["first_day"] = d.groupby("country_code")["date"].min()
    countries = meta.reset_index()[COUNTRIES.column_names].sort_values("country_code").reset_index(drop=True)
    return d, m, countries


def make_fetchers(_, snapshot_date):
    session = make_session()
    cache = {}

    def parsed():
        if "x" not in cache:
            cache["x"] = tidy(download(session))
        return cache["x"]

    return {
        "policy_rates_daily": lambda previous: parsed()[0],
        "policy_rates_monthly": lambda previous: parsed()[1],
        "countries": lambda previous: parsed()[2],
    }


# ---------- derived ----------


MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
DATE_IN_NOTE = re.compile(r"(?:(\d{1,2})\s+)?(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{4})", re.I)


def note_dates(note):
    """Days and months named in a BIS break note: ({dates}, {(year, month)} for month-only mentions)."""
    days, months = set(), set()
    for day, mon, year in DATE_IN_NOTE.findall(note if isinstance(note, str) else ""):
        y, m = int(year), MONTHS[mon[:3].lower()]
        if day:
            try:
                days.add(pd.Timestamp(year=y, month=m, day=int(day)))
            except ValueError:
                pass
        else:
            months.add((y, m))
    return days, months


def changes(daily, countries=None):
    if daily is None or daily.empty:
        return pd.DataFrame(columns=CHANGES.column_names)
    d = daily.sort_values(["country_code", "date"]).copy()
    d["old_rate_pct"] = d.groupby("country_code")["rate_pct"].shift()
    moves = d[d["old_rate_pct"].notna() & (d["rate_pct"].round(4) != d["old_rate_pct"].round(4))].copy()
    moves = moves.rename(columns={"rate_pct": "new_rate_pct"})
    moves["change_bp"] = ((moves["new_rate_pct"] - moves["old_rate_pct"]) * 100).round(1)
    moves["direction"] = moves["change_bp"].map(lambda v: "hike" if v > 0 else "cut")
    notes = {} if countries is None else {c: note_dates(n) for c, n in zip(countries["country_code"], countries["breaks_note"])}
    def is_break(row):
        days, months = notes.get(row.country_code, (set(), set()))
        return row.date in days or (row.date.year, row.date.month) in months
    moves["possible_break"] = [is_break(r) for r in moves.itertuples()] if len(moves) else []
    return moves[CHANGES.column_names].reset_index(drop=True)


def latest(daily, moves=None):
    if daily is None or daily.empty:
        return pd.DataFrame(columns=LATEST.column_names)
    moves = changes(daily) if moves is None else moves
    moves = moves[~moves["possible_break"]] if "possible_break" in moves else moves
    rows = []
    for code, d in daily.sort_values("date").groupby("country_code"):
        s = d.set_index("date")["rate_pct"]
        last_day, rate = s.index[-1], s.iloc[-1]
        before = s[s.index <= last_day - pd.DateOffset(years=1)]
        since = s[s.index >= "2022-01-01"]
        mv = moves[moves["country_code"] == code]
        peak = since.max() if len(since) else None
        rows.append({"country_code": code, "country": d["country"].iloc[-1], "date": last_day, "rate_pct": rate,
                     "change_12m_bp": round((rate - before.iloc[-1]) * 100, 1) if len(before) else None,
                     "last_move_date": mv["date"].iloc[-1] if len(mv) else None,
                     "last_move_bp": mv["change_bp"].iloc[-1] if len(mv) else None,
                     "peak_since_2022_pct": peak, "from_peak_bp": round((rate - peak) * 100, 1) if peak is not None else None})
    return pd.DataFrame(rows, columns=LATEST.column_names).sort_values("country").reset_index(drop=True)


def derive(frames):
    daily = frames.get("policy_rates_daily")
    moves = changes(daily, frames.get("countries"))
    return {"rate_changes": moves, "latest": latest(daily, moves)}


# ---------- description ----------


def overview(frames):
    daily = (frames or {}).get("policy_rates_daily")
    if daily is None or daily.empty:
        return "(computed when the dataset is built)"
    lt = latest(daily, changes(daily, (frames or {}).get("countries")))
    show = lt[lt["country_code"].isin(["US", "XM", "GB", "JP", "CN", "IN", "ID", "MY", "TH", "PH", "KR", "BR", "TR"])]
    lines = [f"{daily['country_code'].nunique()} central banks; daily data to {daily['date'].max():%d %b %Y}.", "",
             "| Central bank of | Rate | 12-month change | Last move | Below 2022-23 peak |", "|---|---|---|---|---|"]
    bp = lambda v: f"{v:+.0f} bp" if pd.notna(v) else "–"
    for r in show.itertuples():
        last = f"{r.last_move_bp:+.0f} bp on {r.last_move_date:%d %b %Y}" if pd.notna(r.last_move_bp) else "–"
        lines.append(f"| {r.country} | {r.rate_pct:.2f}% | {bp(r.change_12m_bp)} | {last} | {bp(r.from_peak_bp)} |")
    return "\n".join(lines)


def describe(snapshot_date, tables_written, frames=None):
    return "\n".join([
        "**The interest rates central banks set**: policy rates for more than 40 central banks, including the Fed, the "
        "ECB, Bank Indonesia and the Bank of Japan, daily and monthly (back to the 1940s for some), with every rate "
        "move listed and a summary of where each bank stands now.",
        "",
        "## Why this dataset",
        "",
        "- **Banking and macro analysis**: hiking and cutting cycles, how closely emerging markets follow the Fed, "
        "real rates against inflation, and the 2022-23 tightening and its unwinding.",
        "- **Every move, ready to use**: a table of each change with its size in basis points, built from the daily "
        "data, with moves on documented break dates flagged.",
        "- **Breaks documented**: the BIS notes on series breaks (for example Bank Indonesia's 2016 switch from the BI "
        "Rate to the 7-day reverse repo rate, which was not a cut) are kept with each country.",
        "",
        "## Files",
        "",
        files_markdown(tables_written),
        "",
        "## Overview",
        "",
        overview(frames),
        "",
        "## How to read it",
        "",
        "- **Policy rate** means the rate each central bank uses to signal its stance, which differs by country "
        "(overnight rate, repo rate, deposit rate, the midpoint of a target range ...); `countries.breaks_note` "
        "describes changes of instrument where the BIS documents them.",
        "- **Breaks**: a jump on the date of a change of instrument is not a policy move; check `breaks_note` before "
        "reading a single change as easing or tightening.",
        "- **Not investment advice**: this is statistical data for analysis.",
        "",
        "## Updates",
        "",
        f"Rebuilt weekly from the BIS bulk download. Last update: {snapshot_date:%Y-%m-%d} (UTC).",
        "",
        "## Source and terms",
        "",
        "Bank for International Settlements, Central bank policy rates (WS_CBPOL), https://data.bis.org. BIS "
        "statistics may be used provided the BIS is cited as the source; the BIS does not endorse this dataset and the "
        "data is not investment advice (terms: https://www.bis.org/terms_statistics.htm). Not affiliated with the BIS.",
    ])


SPEC = DatasetSpec(
    name="policy-rates",
    slug="central-bank-policy-rates-daily-bis",
    title="Central Bank Policy Rates: 40+ Banks, Daily",
    subtitle="Fed, ECB, Bank Indonesia and more: every rate move since the 1940s, from the BIS",
    license="other",
    keywords=["finance", "banking", "economics", "time series analysis", "tabular"],
    tables=TABLES,
    sources="Bank for International Settlements, Central bank policy rates (WS_CBPOL), https://data.bis.org; cite the "
            "BIS. Built weekly by https://github.com/daniel766hi/kaggle-compe",
    make_fetchers=make_fetchers,
    derive=derive,
    describe=describe,
    cover=ASSETS / "policy-rates-cover.png",
    update_frequency="weekly",
    run_weekday=3,  # Thursday
)
