"""Global electricity: generation by source, capacity and emissions for 220+ countries and regions (Ember).

Source: Ember (https://ember-energy.org), yearly and monthly electricity data, CC BY 4.0. Ember compiles national
statistics (IEA, EIA, Eurostat, national grid operators and ministries) into one consistent series per country and
fuel. Yearly data covers every country; monthly data covers the larger economies. Ember revises recent months.
"""

import io
import logging
from pathlib import Path

import pandas as pd

from ..http import make_session as base_session
from ..schema import Column, DatasetSpec, Table, files_markdown

log = logging.getLogger(__name__)

ASSETS = Path(__file__).resolve().parents[2] / "assets"
BASE = "https://files.ember-energy.org/public-downloads/generation/outputs/"
YEARLY = BASE + "release_generation_yearly_global.csv"
MONTHLY = BASE + "release_generation_monthly_global.csv"

SOURCES = "coal, gas, other fossil, nuclear, hydro, wind, solar, bioenergy, other renewables, net imports"
AGGREGATES = "fossil, renewables, clean, wind and solar, total generation, demand"

YEARLY_T = Table(
    name="electricity_yearly",
    kind="history",
    description="Per country or region, year and source: generation (TWh), share, capacity (GW) and emissions. 1985 to the latest full year.",
    key=("area", "year", "source"),
    min_rows=80_000,
    max_shrink=0.02,
    columns=[
        Column("year", "integer", "Year"),
        Column("area", "string", "Country, economy or region (e.g. Indonesia, ASEAN, World)"),
        Column("iso3", "string", "ISO 3166 alpha-3 code (empty for regions)"),
        Column("source", "string", "Electricity source (coal, gas, nuclear, hydro, wind, solar, ...) or an aggregate"),
        Column("is_aggregate", "boolean", "True for aggregates (fossil, clean, total, ...); do not sum with single sources"),
        Column("generation_twh", "number", "Electricity generated (TWh); for demand, electricity consumed"),
        Column("share_pct", "number", "Share of total generation (%)"),
        Column("yoy_pct", "number", "Change in generation from the year before (%)"),
        Column("capacity_gw", "number", "Installed capacity (GW), where Ember reports it"),
        Column("emissions_mtco2e", "number", "Lifecycle emissions of that generation (million tonnes CO2-equivalent)"),
        Column("intensity_gco2e_kwh", "number", "Emissions per kWh of all generation (gCO2e/kWh); on total-generation rows only"),
    ],
)

MONTHLY_T = Table(
    name="electricity_monthly",
    kind="history",
    description="Per country or region, month and source: generation (TWh), share and change from a year before. About 90 larger economies.",
    key=("area", "month", "source"),
    min_rows=150_000,
    max_shrink=0.02,
    columns=[
        Column("month", "datetime", "First day of the month"),
        Column("area", "string", "Country, economy or region"),
        Column("iso3", "string", "ISO 3166 alpha-3 code (empty for regions)"),
        Column("source", "string", "Electricity source or aggregate (same names as in electricity_yearly)"),
        Column("is_aggregate", "boolean", "True for aggregates such as fossil, clean or total generation"),
        Column("generation_twh", "number", "Electricity generated in the month (TWh)"),
        Column("share_pct", "number", "Share of the month's total generation (%)"),
        Column("yoy_pct", "number", "Change from the same month a year before (%)"),
        Column("emissions_mtco2e", "number", "Emissions of that generation (million tonnes CO2-equivalent)"),
    ],
)

AREAS = Table(
    name="areas",
    kind="history",
    description="One row per country or region: continent, Ember region and membership of EU, OECD, G20, G7 and ASEAN.",
    key=("area",),
    min_rows=200,
    max_shrink=0.05,
    columns=[
        Column("area", "string", "Country, economy or region (joins the other tables)"),
        Column("iso3", "string", "ISO 3166 alpha-3 code (empty for regions)"),
        Column("area_type", "string", "'Country or economy' or 'Region'"),
        Column("continent", "string", "Continent"),
        Column("ember_region", "string", "Ember's region grouping"),
        Column("eu", "boolean", "EU member"),
        Column("oecd", "boolean", "OECD member"),
        Column("g20", "boolean", "G20 member"),
        Column("g7", "boolean", "G7 member"),
        Column("asean", "boolean", "ASEAN member"),
    ],
)

SUMMARY = Table(
    name="country_summary",
    kind="derived",
    description="One row per country: latest year's power mix, carbon intensity and how much the clean share moved in 5 years.",
    key=("area",),
    min_rows=0,
    columns=[
        Column("area", "string", "Country or economy"),
        Column("iso3", "string", "ISO alpha-3 code"),
        Column("year", "integer", "Latest year with data"),
        Column("generation_twh", "number", "Total generation (TWh)"),
        Column("coal_pct", "number", "Coal share of generation (%)"),
        Column("gas_pct", "number", "Gas share (%)"),
        Column("nuclear_pct", "number", "Nuclear share (%)"),
        Column("hydro_pct", "number", "Hydro share (%)"),
        Column("wind_solar_pct", "number", "Wind and solar share (%)"),
        Column("clean_pct", "number", "Clean share: renewables plus nuclear (%)"),
        Column("clean_pct_change_5y", "number", "Change in clean share over 5 years (percentage points)"),
        Column("intensity_gco2e_kwh", "number", "Carbon intensity of generation (gCO2e/kWh)"),
    ],
)

TABLES = [YEARLY_T, MONTHLY_T, AREAS, SUMMARY]

# ---------- download and parsing ----------


def make_session():
    return base_session()


def download(session, url):
    resp = session.get(url, timeout=600)
    resp.raise_for_status()
    return pd.read_csv(io.BytesIO(resp.content), low_memory=False)


COMMON = {"Area": "area", "ISO 3 code": "iso3", "Electricity source": "source", "Is aggregated source": "is_aggregate",
          "Generation (TWh)": "generation_twh", "Share of generation (%)": "share_pct",
          "Generation YoY change (%)": "yoy_pct", "Emissions (MtCO2e)": "emissions_mtco2e"}


def tidy_yearly(raw):
    df = raw.rename(columns={**COMMON, "Year": "year", "Capacity (GW)": "capacity_gw",
                             "Emissions intensity (gCO2e/kWh)": "intensity_gco2e_kwh"})
    df["source"] = df["source"].str.strip()
    df["is_aggregate"] = df["is_aggregate"].astype(str).str.lower().eq("true")
    # Ember repeats the area's intensity on every row; it describes the whole mix, so keep it on the total only.
    df["intensity_gco2e_kwh"] = df["intensity_gco2e_kwh"].where(df["source"] == "Total generation")
    return df[YEARLY_T.column_names].sort_values(["area", "year", "source"]).reset_index(drop=True)


def tidy_monthly(raw):
    df = raw.rename(columns={**COMMON, "Date": "month"})
    df["month"] = pd.to_datetime(df["month"])
    df["source"] = df["source"].str.strip()
    df["is_aggregate"] = df["is_aggregate"].astype(str).str.lower().eq("true")
    return df[MONTHLY_T.column_names].sort_values(["area", "month", "source"]).reset_index(drop=True)


def tidy_areas(raw):
    flags = {"EU member": "eu", "OECD member": "oecd", "G20 member": "g20", "G7 member": "g7", "ASEAN member": "asean"}
    df = raw.rename(columns={"Area": "area", "ISO 3 code": "iso3", "Area type": "area_type", "Continent": "continent",
                             "Ember region": "ember_region", **flags})
    df = df.sort_values("Year").groupby("area", as_index=False).last()  # latest membership
    for col in flags.values():
        df[col] = df[col].astype(str).str.lower().eq("true")
    return df[AREAS.column_names].sort_values("area").reset_index(drop=True)


def make_fetchers(_, snapshot_date):
    session = make_session()
    cache = {}

    def yearly():
        if "y" not in cache:
            cache["y"] = download(session, YEARLY)
        return cache["y"]

    return {
        "electricity_yearly": lambda previous: tidy_yearly(yearly()),
        "electricity_monthly": lambda previous: tidy_monthly(download(session, MONTHLY)),
        "areas": lambda previous: tidy_areas(yearly()),
    }


# ---------- derived ----------


def summary(yearly, areas):
    if yearly is None or yearly.empty:
        return pd.DataFrame(columns=SUMMARY.column_names)
    countries = set(areas.loc[areas["area_type"] == "Country or economy", "area"]) if areas is not None else None
    y = yearly if countries is None else yearly[yearly["area"].isin(countries)]
    share = y.pivot_table(index=["area", "year"], columns="source", values="share_pct", aggfunc="first")
    total = y[y["source"] == "Total generation"].set_index(["area", "year"])
    rows = []
    for area, s in share.groupby(level="area"):
        s = s.droplevel("area")
        if "Total generation" not in s or s["Total generation"].dropna().empty:
            continue
        year = int(s["Total generation"].dropna().index.max())
        def get(col, yr=year, missing=0.0):
            # A source Ember does not list for a country (e.g. nuclear in Indonesia) generates nothing there.
            if yr not in s.index or pd.isna(s.at[yr, "Total generation"]):
                return None
            return round(float(s.at[yr, col]), 2) if col in s and pd.notna(s.at[yr, col]) else missing
        clean, clean_5 = get("Clean"), get("Clean", year - 5)
        t = total.loc[(area, year)]
        rows.append({"area": area, "iso3": t["iso3"], "year": year, "generation_twh": t["generation_twh"],
                     "coal_pct": get("Coal"), "gas_pct": get("Gas"), "nuclear_pct": get("Nuclear"), "hydro_pct": get("Hydro"),
                     "wind_solar_pct": get("Wind and solar"), "clean_pct": clean,
                     "clean_pct_change_5y": round(clean - clean_5, 2) if clean is not None and clean_5 is not None else None,
                     "intensity_gco2e_kwh": t["intensity_gco2e_kwh"]})
    return pd.DataFrame(rows, columns=SUMMARY.column_names).sort_values("generation_twh", ascending=False).reset_index(drop=True)


def derive(frames):
    return {"country_summary": summary(frames.get("electricity_yearly"), frames.get("areas"))}


# ---------- description ----------


def overview(frames):
    s = summary((frames or {}).get("electricity_yearly"), (frames or {}).get("areas"))
    if s.empty:
        return "(computed when the dataset is built)"
    year = int(s["year"].max())
    lines = [f"Latest full year: **{year}**. The ten largest power systems:", "",
             "| Country | Generation (TWh) | Coal | Gas | Wind + solar | Clean | Clean share, 5-year change |",
             "|---|---|---|---|---|---|---|"]
    fmt = lambda v, suf="%": f"{v:.1f}{suf}" if pd.notna(v) else "–"
    for r in s[s["year"] == year].head(10).itertuples():
        lines.append(f"| {r.area} | {r.generation_twh:,.0f} | {fmt(r.coal_pct)} | {fmt(r.gas_pct)} | {fmt(r.wind_solar_pct)} | "
                     f"{fmt(r.clean_pct)} | {fmt(r.clean_pct_change_5y, ' pp')} |")
    idn = s[s["area"] == "Indonesia"]
    if not idn.empty:
        r = idn.iloc[0]
        lines += ["", f"Indonesia ({int(r['year'])}): {r['generation_twh']:,.0f} TWh, coal {fmt(r['coal_pct'])}, "
                      f"clean {fmt(r['clean_pct'])}, {r['intensity_gco2e_kwh']:.0f} gCO2e/kWh."]
    return "\n".join(lines)


def describe(snapshot_date, tables_written, frames=None):
    return "\n".join([
        "**How the world makes its electricity**: generation by source (coal, gas, nuclear, hydro, wind, solar, "
        "bioenergy and more), installed capacity and emissions for 220+ countries and regions, yearly since 1985 and "
        "monthly for the larger economies, from Ember's open electricity data.",
        "",
        "## Why this dataset",
        "",
        "- **The energy transition in numbers**: how fast solar and wind grow, which countries still run on coal, and "
        "how carbon intensity falls (or does not).",
        "- **Tidy and consistent**: one row per area, period and source, with shares and year-on-year change already "
        "computed, plus a one-row-per-country summary of the latest power mix.",
        "- **Asia included**: Indonesia, Vietnam, the Philippines, India and the rest of ASEAN in the yearly data.",
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
        "- **Aggregates** (`is_aggregate` = True: fossil, renewables, clean, wind and solar, total generation, "
        "demand) overlap the single sources; sum only rows where `is_aggregate` is False.",
        "- **Clean** = renewables plus nuclear. **Emissions** are lifecycle emissions of generation.",
        "- **Monthly data** covers about 90 economies; countries such as Indonesia appear in the yearly data only.",
        "- **Revisions**: Ember revises recent months and years as national statistics are finalized.",
        "",
        "## Updates",
        "",
        f"Rebuilt monthly from Ember's latest release. Last update: {snapshot_date:%Y-%m-%d} (UTC).",
        "",
        "## Source and license",
        "",
        "Ember, Yearly and Monthly Electricity Data (https://ember-energy.org/data/), licensed CC BY 4.0. Cite Ember "
        "when you use it. This dataset only reorganizes the published data and is not affiliated with Ember.",
    ])


SPEC = DatasetSpec(
    name="electricity",
    slug="global-electricity-mix-generation-emissions",
    title="Global Electricity Mix: Coal, Gas, Solar, Wind",
    subtitle="Generation, capacity and emissions by source for 220+ countries, monthly update",
    license="CC-BY-4.0",
    keywords=["environment", "economics", "time series analysis", "tabular", "data visualization"],
    tables=TABLES,
    sources="Ember, Yearly and Monthly Electricity Data (https://ember-energy.org/data/), CC BY 4.0. "
            "Built monthly by https://github.com/daniel766hi/kaggle-compe",
    make_fetchers=make_fetchers,
    derive=derive,
    describe=describe,
    cover=ASSETS / "electricity-cover.png",
    update_frequency="monthly",
    run_days=(9, 23),  # Ember publishes monthly data through the month; twice a month keeps it close
)
