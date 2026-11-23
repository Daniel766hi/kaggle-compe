"""ASEAN and G20 economies: 30 World Development Indicators per country and year since 1990 (World Bank).

Source: World Bank World Development Indicators via the World Bank API (https://api.worldbank.org/v2), licensed
CC BY 4.0. The indicators cover growth, prices, credit and interest rates, trade and investment, industry
structure, natural-resource rents, labour, digital access and logistics. The World Bank revises past values when
national statistics change, so each run rebuilds the full panel.
"""

import logging
import time
from pathlib import Path

import pandas as pd

from ..http import make_session as base_session
from ..schema import Column, DatasetSpec, Table, files_markdown

log = logging.getLogger(__name__)

ASSETS = Path(__file__).resolve().parents[2] / "assets"
API = "https://api.worldbank.org/v2"
FIRST_YEAR = 1990

ASEAN = ["BRN", "KHM", "IDN", "LAO", "MYS", "MMR", "PHL", "SGP", "THA", "VNM", "TLS"]  # Timor-Leste joined in 2025
G20 = ["ARG", "AUS", "BRA", "CAN", "CHN", "FRA", "DEU", "IND", "IDN", "ITA", "JPN", "KOR", "MEX", "RUS", "SAU",
       "ZAF", "TUR", "GBR", "USA"]
AGGREGATES = ["WLD", "EAS", "EUU", "LMC", "UMC", "HIC"]  # world, East Asia & Pacific, EU, income groups
COUNTRIES = sorted(set(ASEAN + G20)) + AGGREGATES

INDICATORS = {  # code -> topic
    "NY.GDP.MKTP.CD": "economy", "NY.GDP.MKTP.KD.ZG": "economy", "NY.GDP.PCAP.PP.KD": "economy",
    "FP.CPI.TOTL.ZG": "prices", "NV.IND.MANF.ZS": "structure", "NV.AGR.TOTL.ZS": "structure",
    "NV.SRV.TOTL.ZS": "structure", "NY.GDP.MINR.RT.ZS": "resources", "NY.GDP.COAL.RT.ZS": "resources",
    "NY.GDP.PETR.RT.ZS": "resources", "NE.EXP.GNFS.ZS": "trade", "NE.IMP.GNFS.ZS": "trade",
    "TX.VAL.TECH.MF.ZS": "trade", "BN.CAB.XOKA.GD.ZS": "external", "BX.KLT.DINV.WD.GD.ZS": "external",
    "FI.RES.TOTL.CD": "external", "PA.NUS.FCRF": "external", "FS.AST.PRVT.GD.ZS": "finance", "FR.INR.LEND": "finance",
    "FR.INR.RINR": "finance", "GC.DOD.TOTL.GD.ZS": "finance", "SP.POP.TOTL": "people", "SP.URB.TOTL.IN.ZS": "people",
    "SL.UEM.TOTL.ZS": "labour", "SL.TLF.CACT.ZS": "labour", "SI.POV.GINI": "people", "EG.ELC.ACCS.ZS": "infrastructure",
    "IT.NET.USER.ZS": "infrastructure", "LP.LPI.OVRL.XQ": "infrastructure", "SE.TER.ENRR": "people",
}

VALUES = Table(
    name="indicator_values",
    kind="history",
    description="One row per country, indicator and year since 1990: the indicator's value (see indicators for names and units).",
    key=("iso3", "indicator", "year"),
    min_rows=20_000,
    max_shrink=0.02,
    columns=[
        Column("iso3", "string", "Country or aggregate code (ISO alpha-3, or a World Bank code such as WLD)"),
        Column("country", "string", "Country or aggregate name"),
        Column("indicator", "string", "Indicator code (joins indicators.indicator), e.g. NY.GDP.MKTP.KD.ZG"),
        Column("year", "integer", "Year"),
        Column("value", "number", "Value, in the unit given by the indicator's name"),
    ],
)

INDICATORS_T = Table(
    name="indicators",
    kind="history",
    description="One row per indicator: code, name (with unit), topic, source organization and the World Bank's definition.",
    key=("indicator",),
    min_rows=25,
    columns=[
        Column("indicator", "string", "World Bank indicator code"),
        Column("name", "string", "Name, including the unit, e.g. 'GDP growth (annual %)'"),
        Column("topic", "string", "Topic, e.g. economy, prices, trade, finance, labour, infrastructure"),
        Column("source_organization", "string", "Organization that produces the underlying data"),
        Column("definition", "string", "World Bank definition of the indicator"),
    ],
)

COUNTRIES_T = Table(
    name="countries",
    kind="history",
    description="One row per country or aggregate: region, income group and whether it belongs to ASEAN or the G20.",
    key=("iso3",),
    min_rows=25,
    columns=[
        Column("iso3", "string", "Country or aggregate code"),
        Column("country", "string", "Name"),
        Column("region", "string", "World Bank region (empty for aggregates)"),
        Column("income_group", "string", "World Bank income group (empty for aggregates)"),
        Column("asean", "boolean", "ASEAN member"),
        Column("g20", "boolean", "G20 member (the EU is included among the aggregates)"),
        Column("is_aggregate", "boolean", "True for world, regional and income-group aggregates"),
    ],
)

LATEST = Table(
    name="latest",
    kind="derived",
    description="One row per country and indicator: latest value, the value 10 years earlier, and the change between them.",
    key=("iso3", "indicator"),
    min_rows=0,
    columns=[
        Column("iso3", "string", "Country or aggregate code"),
        Column("country", "string", "Name"),
        Column("indicator", "string", "Indicator code"),
        Column("latest_year", "integer", "Latest year with a value"),
        Column("latest_value", "number", "Value in that year"),
        Column("value_10y_before", "number", "Value 10 years before the latest year (empty if missing)"),
        Column("change_10y", "number", "latest_value minus value_10y_before"),
    ],
)

TABLES = [VALUES, INDICATORS_T, COUNTRIES_T, LATEST]

# ---------- download ----------


def make_session():
    return base_session()


def get_json(session, path, **params):
    params = {"format": "json", "per_page": 20000, **params}
    for attempt in range(4):
        resp = session.get(f"{API}/{path}", params=params, timeout=120)
        if resp.status_code in (429, 500, 502, 503, 504) and attempt < 3:
            time.sleep(10 * (attempt + 1))
            continue
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list) and len(data) == 2:
            return data[1] or []
        # The API answers errors with HTTP 200 and a message object.
        raise RuntimeError(f"World Bank API error for {path}: {str(data)[:300]}")
    raise RuntimeError(f"World Bank API kept failing for {path}")


def fetch_values(session, snapshot_date):
    rows = []
    end = snapshot_date.year
    for code in INDICATORS:
        try:
            data = get_json(session, f"country/{';'.join(COUNTRIES)}/indicator/{code}", date=f"{FIRST_YEAR}:{end}")
        except RuntimeError as exc:
            log.warning("Skipping %s: %s", code, exc)  # a retired indicator must not stop the others
            continue
        for d in data:
            if d.get("value") is not None:
                rows.append({"iso3": d["countryiso3code"] or d["country"]["id"], "country": d["country"]["value"],
                             "indicator": code, "year": int(d["date"]), "value": float(d["value"])})
        time.sleep(0.3)
    df = pd.DataFrame(rows, columns=VALUES.column_names)
    return df.sort_values(["iso3", "indicator", "year"]).reset_index(drop=True)


def fetch_indicators(session):
    rows = []
    for code, topic in INDICATORS.items():
        try:
            meta = get_json(session, f"indicator/{code}")
        except RuntimeError as exc:
            log.warning("No metadata for %s: %s", code, exc)
            continue
        if meta:
            m = meta[0]
            rows.append({"indicator": code, "name": m.get("name"), "topic": topic,
                         "source_organization": (m.get("sourceOrganization") or "").strip() or None,
                         "definition": (m.get("sourceNote") or "").strip() or None})
    return pd.DataFrame(rows, columns=INDICATORS_T.column_names)


def fetch_countries(session):
    data = get_json(session, f"country/{';'.join(COUNTRIES)}")
    rows = []
    for d in data:
        iso3 = d["id"]
        agg = (d.get("region") or {}).get("value") == "Aggregates"
        rows.append({"iso3": iso3, "country": d["name"], "region": None if agg else (d.get("region") or {}).get("value"),
                     "income_group": None if agg else (d.get("incomeLevel") or {}).get("value"),
                     "asean": iso3 in ASEAN, "g20": iso3 in G20, "is_aggregate": agg})
    return pd.DataFrame(rows, columns=COUNTRIES_T.column_names).sort_values("iso3").reset_index(drop=True)


def make_fetchers(_, snapshot_date):
    session = make_session()
    return {
        "indicator_values": lambda previous: fetch_values(session, snapshot_date),
        "indicators": lambda previous: fetch_indicators(session),
        "countries": lambda previous: fetch_countries(session),
    }


# ---------- derived ----------


def latest(values):
    if values is None or values.empty:
        return pd.DataFrame(columns=LATEST.column_names)
    v = values.sort_values("year")
    last = v.groupby(["iso3", "indicator"]).tail(1).rename(columns={"year": "latest_year", "value": "latest_value"})
    before = v.rename(columns={"year": "y10", "value": "value_10y_before"})[["iso3", "indicator", "y10", "value_10y_before"]]
    last = last.assign(y10=last["latest_year"] - 10).merge(before, on=["iso3", "indicator", "y10"], how="left")
    last["change_10y"] = (last["latest_value"] - last["value_10y_before"]).round(4)
    return last[LATEST.column_names].sort_values(["iso3", "indicator"]).reset_index(drop=True)


def derive(frames):
    return {"latest": latest(frames.get("indicator_values"))}


# ---------- description ----------


def overview(frames):
    values, names = (frames or {}).get("indicator_values"), (frames or {}).get("indicators")
    if values is None or values.empty:
        return "(computed when the dataset is built)"
    lt = latest(values)
    show = {"NY.GDP.MKTP.KD.ZG": "GDP growth %", "FP.CPI.TOTL.ZG": "Inflation %", "NY.GDP.PCAP.PP.KD": "GDP per capita (PPP)",
            "FS.AST.PRVT.GD.ZS": "Private credit % GDP", "NV.IND.MANF.ZS": "Manufacturing % GDP"}
    asean = [c for c in ASEAN if c in set(lt["iso3"])]
    wide = lt[lt["indicator"].isin(show) & lt["iso3"].isin(asean)].pivot(index="country", columns="indicator", values="latest_value")
    lines = [f"{values['iso3'].nunique()} countries and aggregates, {values['indicator'].nunique()} indicators, "
             f"{values['year'].min()} to {values['year'].max()}; {len(values):,} values.", "",
             "Latest values for ASEAN (each indicator's latest year):", "",
             "| Country | " + " | ".join(show.values()) + " |", "|---" * (len(show) + 1) + "|"]
    fmt = lambda c, v: "–" if pd.isna(v) else (f"{v:,.0f}" if c == "NY.GDP.PCAP.PP.KD" else f"{v:.1f}")
    for country, r in wide.iterrows():
        lines.append(f"| {country} | " + " | ".join(fmt(c, r.get(c)) for c in show) + " |")
    return "\n".join(lines)


def describe(snapshot_date, tables_written, frames=None):
    names = (frames or {}).get("indicators")
    listing = ""
    if names is not None and not names.empty:
        listing = "\n".join(f"- `{r.indicator}`: {r.name}" for r in names.itertuples())
    return "\n".join([
        "**A ready-to-use macro panel for Southeast Asia and the G20**: 30 World Bank indicators on growth, "
        "inflation, credit and interest rates, trade and investment, industry structure, mining and energy rents, "
        "jobs, digital access and logistics, for the 11 ASEAN members, the G20 economies and world and income-group "
        "aggregates, every year since 1990.",
        "",
        "## Why this dataset",
        "",
        "- **For comparisons a bank, consultancy or investor makes**: Indonesia vs Vietnam vs the Philippines on "
        "growth, credit depth, manufacturing share and logistics performance, in one tidy table.",
        "- **Curated, not dumped**: 30 indicators chosen for business analysis instead of 1,400, each with its "
        "definition and source.",
        "- **Analysis-ready**: long format with a country table (ASEAN / G20 flags, income group) and a latest-value "
        "table with 10-year change.",
        "",
        "## Files",
        "",
        files_markdown(tables_written),
        "",
        "## Overview",
        "",
        overview(frames),
        "",
        "## Indicators",
        "",
        listing or "(listed when the dataset is built)",
        "",
        "## How to read it",
        "",
        "- **Units** are in each indicator's name (current US$, %, % of GDP, index).",
        "- **Gaps are normal**: some indicators are published every few years (e.g. Gini, logistics performance) or "
        "not for every country; there are no rows for missing values.",
        "- **Revisions**: the World Bank revises past values; each update rebuilds the full panel.",
        "",
        "## Updates",
        "",
        f"Rebuilt monthly from the World Bank API. Last update: {snapshot_date:%Y-%m-%d} (UTC).",
        "",
        "## Source and license",
        "",
        "World Bank, World Development Indicators (https://databank.worldbank.org/source/world-development-indicators), "
        "licensed CC BY 4.0. Cite the World Bank and the original source organization of each indicator. Not "
        "affiliated with the World Bank.",
    ])


SPEC = DatasetSpec(
    name="macro-asean",
    slug="asean-g20-macro-indicators-world-bank",
    title="ASEAN & G20 Economies: 30 World Bank Indicators",
    subtitle="Growth, inflation, credit, trade, FDI, industry and logistics by year since 1990",
    license="CC-BY-4.0",
    keywords=["economics", "finance", "asia", "banking", "tabular"],
    tables=TABLES,
    sources="World Bank, World Development Indicators (https://api.worldbank.org/v2), CC BY 4.0. "
            "Built monthly by https://github.com/daniel766hi/kaggle-compe",
    make_fetchers=make_fetchers,
    derive=derive,
    describe=describe,
    cover=ASSETS / "macro-asean-cover.png",
    update_frequency="monthly",
    run_days=(16,),
)
