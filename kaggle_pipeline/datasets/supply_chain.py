"""Global supply chain monitor: daily maritime trade by country, chokepoint transits, ports, and the
New York Fed's Global Supply Chain Pressure Index.

Sources:
- IMF PortWatch (https://portwatch.imf.org): estimates from satellite AIS ship positions of daily port
  calls and trade volumes (metric tons) for every country with seaports, daily transits through 28
  maritime chokepoints, and a profile of every port. PortWatch's query API is shared by all its users
  and often over its rate limit, so the full tables are taken from its bulk CSV downloads instead.
  PortWatch refreshes them weekly (Tuesdays); while a file is being regenerated the download answers
  202, and the run waits and retries.
- Federal Reserve Bank of New York: the Global Supply Chain Pressure Index (GSCPI), monthly since 1998.
"""

import io
import logging
import time
from pathlib import Path

import pandas as pd

from ..http import make_session as base_session
from ..schema import Column, DatasetSpec, Table, files_markdown

log = logging.getLogger(__name__)

ASSETS = Path(__file__).resolve().parents[2] / "assets"
DOWNLOAD = "https://portwatch.imf.org/api/download/v1/items/{item}/csv?layers=0"
ITEMS = {  # PortWatch ArcGIS item ids
    "country_daily": "e5d926daf73844889d670f7adc95b791",  # Daily_Trade_Data_REG
    "chokepoint_daily": "3da2b9ca97684916b75c4013f95d18ab",  # Daily_Chokepoints_Data
    "ports": "acc668d199d1472abaaf2467133d4ca4",  # PortWatch_ports_database
}
GSCPI = "https://www.newyorkfed.org/medialibrary/research/interactives/gscpi/downloads/gscpi_data.xlsx"
WAIT_S, WAIT_ROUNDS = 60, 20  # a file being regenerated is retried for up to 20 minutes

VESSELS = ["container", "dry_bulk", "general_cargo", "roro", "tanker"]
VESSEL_NAMES = {"container": "container ships", "dry_bulk": "dry bulk carriers", "general_cargo": "general cargo ships",
                "roro": "roll-on/roll-off ships", "tanker": "tankers"}


def flows(prefix, unit, what):
    cols = [Column(f"{prefix}_{v}", "number" if unit else "integer", f"{what} by {VESSEL_NAMES[v]}{unit}")
            for v in VESSELS]
    cols.append(Column(f"{prefix}_cargo", "number" if unit else "integer",
                       f"{what} by all cargo ships (all but tankers){unit}"))
    cols.append(Column(prefix, "number" if unit else "integer", f"{what}, all ships{unit}"))
    return cols


COUNTRY = Table(
    name="country_daily",
    kind="history",  # PortWatch revises recent days; each run takes its full current table
    fmt="parquet",
    description="Per country (and world and regional aggregates) and day: port calls and trade volumes by ship type.",
    key=("iso3", "date"),
    min_rows=100_000,
    columns=[
        Column("date", "datetime", "Day (UTC)"),
        Column("iso3", "string", "ISO 3166 alpha-3 code, or an aggregate code such as WLD (world)"),
        Column("country", "string", "Country or aggregate name"),
        Column("is_aggregate", "boolean", "True for the world and regional aggregates"),
        *flows("portcalls", "", "Port calls"),
        *flows("import", " (metric tons)", "Imports"),
        *flows("export", " (metric tons)", "Exports"),
        Column("shipment", "number", "Imports plus exports (metric tons)"),
        Column("portcalls_container_30ma", "number", "Container port calls, 30-day moving average"),
        Column("portcalls_container_30ma_yoy", "number", "Change of that average vs the same day a year before (%)"),
        Column("shipment_30ma", "number", "Imports plus exports, 30-day moving average (metric tons)"),
        Column("shipment_30ma_yoy", "number", "Change of that average vs the same day a year before (%)"),
    ],
)

CHOKEPOINTS = Table(
    name="chokepoint_daily",
    kind="history",
    description="Per chokepoint and day: ship transits by type and their carrying capacity, 28 straits and canals.",
    key=("chokepoint_id", "date"),
    min_rows=10_000,
    columns=[
        Column("date", "datetime", "Day (UTC)"),
        Column("chokepoint_id", "string", "PortWatch id (chokepoint1 ... chokepoint28)"),
        Column("chokepoint", "string", "Name, e.g. Malacca Strait, Suez Canal"),
        *flows("transits", "", "Transits"),
        *flows("capacity", " (deadweight tons)", "Carrying capacity of transiting ships"),
    ],
)

PORTS = Table(
    name="ports",
    kind="history",
    description="Profile of every port PortWatch tracks: location, yearly ship visits by type, main industries.",
    key=("port_id",),
    min_rows=500,
    max_shrink=0.05,  # PortWatch occasionally merges or drops small ports
    columns=[
        Column("port_id", "string", "PortWatch port id"),
        Column("port", "string", "Port name"),
        Column("country", "string", "Country"),
        Column("iso3", "string", "ISO 3166 alpha-3 country code"),
        Column("continent", "string", "Region as PortWatch groups it"),
        Column("locode", "string", "UN/LOCODE"),
        Column("latitude", "number", "Latitude"),
        Column("longitude", "number", "Longitude"),
        Column("vessels_total", "integer", "Ships calling per year (all types)"),
        *[Column(f"vessels_{v}", "integer", f"Ships calling per year: {VESSEL_NAMES[v]}") for v in VESSELS],
        Column("industry_1", "string", "Main industry of the goods handled"),
        Column("industry_2", "string", "Second industry"),
        Column("industry_3", "string", "Third industry"),
        Column("share_of_country_imports", "number", "Share of the country's seaborne imports (%)"),
        Column("share_of_country_exports", "number", "Share of the country's seaborne exports (%)"),
    ],
)

PRESSURE = Table(
    name="gscpi",
    kind="history",
    description="New York Fed Global Supply Chain Pressure Index, monthly since 1998 (0 = average; units: standard deviations).",
    key=("month",),
    min_rows=200,
    columns=[
        Column("month", "datetime", "First day of the month"),
        Column("gscpi", "number", "Index value: standard deviations above (+) or below (-) the average"),
    ],
)

COUNTRY_MONTHLY = Table(
    name="country_monthly",
    kind="derived",
    description="Per country and month: port calls and trade volumes, with the change from the same month a year before.",
    key=("iso3", "month"),
    min_rows=0,
    columns=[
        Column("month", "datetime", "First day of the month"),
        Column("iso3", "string", "ISO alpha-3 code or aggregate code"),
        Column("country", "string", "Country or aggregate"),
        Column("days", "integer", "Days with data in the month"),
        Column("portcalls", "integer", "Port calls"),
        Column("portcalls_container", "integer", "Container ship port calls"),
        Column("import", "number", "Imports (metric tons)"),
        Column("export", "number", "Exports (metric tons)"),
        Column("import_container", "number", "Imports by container ships (metric tons)"),
        Column("export_container", "number", "Exports by container ships (metric tons)"),
        Column("trade_yoy_pct", "number", "Imports plus exports vs the same month a year before (%)"),
    ],
)

CHOKEPOINT_MONTHLY = Table(
    name="chokepoint_monthly",
    kind="derived",
    description="Per chokepoint and month: average daily transits and capacity, with the change from a year before.",
    key=("chokepoint_id", "month"),
    min_rows=0,
    columns=[
        Column("month", "datetime", "First day of the month"),
        Column("chokepoint_id", "string", "PortWatch id"),
        Column("chokepoint", "string", "Name"),
        Column("days", "integer", "Days with data in the month"),
        Column("transits_per_day", "number", "Average transits per day"),
        Column("container_transits_per_day", "number", "Average container-ship transits per day"),
        Column("tanker_transits_per_day", "number", "Average tanker transits per day"),
        Column("capacity_per_day", "number", "Average carrying capacity per day (deadweight tons)"),
        Column("transits_yoy_pct", "number", "Transits per day vs the same month a year before (%)"),
    ],
)

TABLES = [COUNTRY, CHOKEPOINTS, PORTS, PRESSURE, COUNTRY_MONTHLY, CHOKEPOINT_MONTHLY]

# ---------- download ----------


def make_session():
    return base_session()


def download_csv(session, item, wait_s=WAIT_S, rounds=WAIT_ROUNDS, sleep=time.sleep):
    """A PortWatch table as a DataFrame, waiting while PortWatch regenerates the file."""
    url = DOWNLOAD.format(item=item)
    for attempt in range(rounds):
        resp = session.get(url, timeout=600)
        if resp.status_code == 202:  # {"message": "... being generated ...", "progressInPercent": n}
            log.info("PortWatch %s is being regenerated (%s); waiting", item, resp.text[:160])
            sleep(wait_s)
            continue
        resp.raise_for_status()
        return pd.read_csv(io.BytesIO(resp.content), encoding="utf-8-sig", low_memory=False)
    raise RuntimeError(f"PortWatch file {item} was still being regenerated after {rounds} tries")


def dates(series):
    return pd.to_datetime(series.astype(str).str.slice(0, 10), format="%Y/%m/%d", errors="coerce")


def tidy_country(raw):
    df = raw.drop(columns=["ObjectId"], errors="ignore").rename(columns={
        "ISO3": "iso3", "portcalls_container_30MA": "portcalls_container_30ma",
        "portcalls_container_30MA_yoy_doy": "portcalls_container_30ma_yoy", "shipment_30MA": "shipment_30ma",
        "shipment_30MA_yoy_doy": "shipment_30ma_yoy"})
    df["date"] = dates(df["date"])
    # ISO codes are three letters; PortWatch's aggregates are WLD and numeric region codes.
    df["is_aggregate"] = ~df["iso3"].astype(str).str.fullmatch(r"[A-Z]{3}") | (df["iso3"] == "WLD")
    return df


def tidy_chokepoints(raw):
    df = raw.drop(columns=["ObjectId", "year", "month", "day"], errors="ignore").rename(
        columns={"portid": "chokepoint_id", "portname": "chokepoint", "n_total": "transits"})
    df = df.rename(columns={c: c.replace("n_", "transits_", 1) for c in df.columns if c.startswith("n_")})
    df["date"] = dates(df["date"])
    return df


def tidy_ports(raw):
    return raw.rename(columns={
        "portid": "port_id", "portname": "port", "ISO3": "iso3", "LOCODE": "locode", "lat": "latitude",
        "lon": "longitude", "vessel_count_total": "vessels_total", "vessel_count_container": "vessels_container",
        "vessel_count_dry_bulk": "vessels_dry_bulk", "vessel_count_general_cargo": "vessels_general_cargo",
        "vessel_count_RoRo": "vessels_roro", "vessel_count_tanker": "vessels_tanker",
        "industry_top1": "industry_1", "industry_top2": "industry_2", "industry_top3": "industry_3",
        "share_country_maritime_import": "share_of_country_imports",
        "share_country_maritime_export": "share_of_country_exports"})


def fetch_gscpi(session):
    resp = session.get(GSCPI, timeout=120)
    resp.raise_for_status()
    raw = pd.read_excel(io.BytesIO(resp.content), header=None)  # an .xls workbook despite its name
    raw = raw.iloc[:, :2].set_axis(["date", "gscpi"], axis=1)
    raw["month"] = pd.to_datetime(raw["date"], format="%d-%b-%Y", errors="coerce").dt.to_period("M").dt.to_timestamp()
    out = raw.dropna(subset=["month"]).assign(gscpi=lambda d: pd.to_numeric(d["gscpi"], errors="coerce"))
    return out.dropna(subset=["gscpi"])[["month", "gscpi"]]


def make_fetchers(_, snapshot_date):
    session = make_session()
    return {
        "country_daily": lambda previous: tidy_country(download_csv(session, ITEMS["country_daily"])),
        "chokepoint_daily": lambda previous: tidy_chokepoints(download_csv(session, ITEMS["chokepoint_daily"])),
        "ports": lambda previous: tidy_ports(download_csv(session, ITEMS["ports"])),
        "gscpi": lambda previous: fetch_gscpi(session),
    }


# ---------- derived ----------


def yoy(df, key, value):
    last_year = df[[key, "month", value]].assign(month=df["month"] + pd.DateOffset(years=1))
    merged = df.merge(last_year, on=[key, "month"], how="left", suffixes=("", "_ly"))
    return ((merged[value] / merged[f"{value}_ly"] - 1) * 100).round(2).where(merged[f"{value}_ly"] > 0).to_numpy()


def country_monthly(daily):
    if daily is None or daily.empty:
        return pd.DataFrame(columns=COUNTRY_MONTHLY.column_names)
    d = daily.assign(month=daily["date"].dt.to_period("M").dt.to_timestamp())
    # Only complete months: the latest month is still being filled in.
    last = d["date"].max()
    d = d[d["month"] + pd.offsets.MonthEnd(0) <= last]
    g = d.groupby(["iso3", "month"])
    out = g[["portcalls", "portcalls_container", "import", "export", "import_container", "export_container"]].sum()
    out["days"] = g.size()
    out["country"] = g["country"].first()
    out = out.reset_index()
    out["trade"] = out["import"] + out["export"]
    out["trade_yoy_pct"] = yoy(out, "iso3", "trade")
    return out[COUNTRY_MONTHLY.column_names]


def chokepoint_monthly(daily):
    if daily is None or daily.empty:
        return pd.DataFrame(columns=CHOKEPOINT_MONTHLY.column_names)
    d = daily.assign(month=daily["date"].dt.to_period("M").dt.to_timestamp())
    last = d["date"].max()
    d = d[d["month"] + pd.offsets.MonthEnd(0) <= last]
    g = d.groupby(["chokepoint_id", "month"])
    out = pd.DataFrame({
        "chokepoint": g["chokepoint"].first(), "days": g.size(), "transits_per_day": g["transits"].mean(),
        "container_transits_per_day": g["transits_container"].mean(),
        "tanker_transits_per_day": g["transits_tanker"].mean(), "capacity_per_day": g["capacity"].mean(),
    }).reset_index()
    out["transits_yoy_pct"] = yoy(out, "chokepoint_id", "transits_per_day")
    numeric = ["transits_per_day", "container_transits_per_day", "tanker_transits_per_day", "capacity_per_day"]
    out[numeric] = out[numeric].round(2)
    return out[CHOKEPOINT_MONTHLY.column_names]


def derive(frames):
    return {"country_monthly": country_monthly(frames.get("country_daily")),
            "chokepoint_monthly": chokepoint_monthly(frames.get("chokepoint_daily"))}


# ---------- description ----------


def coverage_markdown(frames):
    rows = ["| Table | Rows | From | To |", "|---|---|---|---|"]
    for name, col in (("country_daily", "date"), ("chokepoint_daily", "date"), ("gscpi", "month")):
        df = (frames or {}).get(name)
        if df is not None and not df.empty:
            rows.append(f"| `{name}` | {len(df):,} | {df[col].min():%Y-%m-%d} | {df[col].max():%Y-%m-%d} |")
    countries = (frames or {}).get("country_daily")
    if countries is not None and not countries.empty:
        n = countries.loc[~countries["is_aggregate"].astype(bool), "iso3"].nunique()
        rows.append(f"\n{n} countries, plus world and regional aggregates.")
    return "\n".join(rows) if len(rows) > 2 else "(computed when the dataset is built)"


def describe(snapshot_date, tables_written, frames=None):
    return "\n".join([
        "**A weekly-updated monitor of global supply chains**: how many ships call at each country's ports and "
        "how much they load and unload every day, how many ships pass through the world's 28 key straits and "
        "canals (Malacca, Suez, Panama, Hormuz, Bab el-Mandeb, Sunda, Lombok, ...), a profile of every major "
        "port, and the New York Fed's Global Supply Chain Pressure Index.",
        "",
        "## Why this dataset",
        "",
        "- **Daily and global**: trade volumes for 190+ countries from January 2019, years before official "
        "trade statistics are published, estimated by the IMF from satellite ship tracking (AIS).",
        "- **Shocks are visible**: COVID-19 port congestion, the Red Sea attacks and the Suez Canal detours, "
        "the Panama Canal drought, and how traffic shifts between routes.",
        "- **Ready to join**: one clean table per level (country, chokepoint, port), monthly summaries with "
        "year-on-year change, and the GSCPI as a macro measure of supply chain stress.",
        "",
        "## Files",
        "",
        files_markdown(tables_written),
        "",
        "## Coverage",
        "",
        coverage_markdown(frames),
        "",
        "## How to read it",
        "",
        "- **Estimates, not customs data**: PortWatch infers trade from ships' positions and draught. Volumes "
        "are in metric tons, not values, and individual days are noisy; compare weekly or monthly sums.",
        "- **Cargo vs tankers**: `*_cargo` columns cover container, dry bulk, general cargo and ro-ro ships; "
        "tankers carry oil, gas and chemicals.",
        "- **Chokepoint capacity** is the deadweight tonnage of transiting ships, a proxy for the cargo that "
        "could pass, not the cargo actually carried.",
        "- **Recent days are revised**: PortWatch updates its tables weekly and can revise the latest weeks; "
        "the monthly tables include complete months only.",
        "- **GSCPI**: 0 is the 1998-2019 average; +1 means pressure one standard deviation above it (the "
        "2021 peak was above +4).",
        "",
        "## Updates",
        "",
        f"Updated weekly, after PortWatch's Tuesday release. Last update: {snapshot_date:%Y-%m-%d} (UTC).",
        "",
        "## Sources and terms",
        "",
        "- IMF PortWatch (https://portwatch.imf.org), based on AIS data from the UN Global Platform. Method: "
        "Arslanalp, Koepke and Verschuur (2021), *Tracking Trade from Space: An Application to Pacific Island "
        "Countries*, IMF Working Paper 21/225. Used under the IMF's terms of use "
        "(https://www.imf.org/external/terms.htm); cite \"IMF PortWatch\" when you use these tables.",
        "- Global Supply Chain Pressure Index: Federal Reserve Bank of New York "
        "(https://www.newyorkfed.org/research/policy/gscpi); Benigno, di Giovanni, Groen and Noble (2022).",
        "",
        "This dataset only reorganizes the published data and is not affiliated with the IMF or the Federal "
        "Reserve Bank of New York.",
    ])


SPEC = DatasetSpec(
    name="supply-chain",
    slug="global-supply-chain-monitor-ports-chokepoints",
    title="Global Supply Chain Monitor: Ports & Chokepoints",
    subtitle="Daily port calls, trade volumes and strait transits for 190+ countries, weekly",
    license="other",
    keywords=["economics", "international relations", "geography", "time series analysis", "tabular"],
    tables=TABLES,
    sources=("IMF PortWatch (https://portwatch.imf.org), IMF terms of use; Federal Reserve Bank of New York "
             "Global Supply Chain Pressure Index. Built weekly by https://github.com/daniel766hi/kaggle-compe"),
    make_fetchers=make_fetchers,
    derive=derive,
    describe=describe,
    cover=ASSETS / "supply-chain-cover.png",
    update_frequency="weekly",
    run_weekday=3,  # Thursday: after PortWatch's Tuesday refresh
)
