"""World airports and runways: every airport, airstrip, heliport and seaplane base in OurAirports.

Source: OurAirports (https://ourairports.com), the open data files published nightly at
https://github.com/davidmegginson/ourairports-data. OurAirports releases its data to the public domain; it is
maintained by volunteers and comes with no guarantee of accuracy. Each run rebuilds the tables from the latest files.
"""

import io
import logging
from pathlib import Path

import pandas as pd

from ..http import make_session as base_session
from ..schema import Column, DatasetSpec, Table, files_markdown

log = logging.getLogger(__name__)

ASSETS = Path(__file__).resolve().parents[2] / "assets"
BASE = "https://raw.githubusercontent.com/davidmegginson/ourairports-data/main/"
FT = 0.3048
PAVED = ("ASP", "CON", "BIT", "PEM", "TAR", "PAV", "ASF", "COP", "MAC")  # surface codes for hard runways

AIRPORTS = Table(
    name="airports",
    kind="history",
    description="Every airport, airstrip, heliport and seaplane base: type, location, country and region, codes and scheduled service.",
    key=("airport_id",),
    min_rows=60_000,
    max_shrink=0.03,
    columns=[
        Column("airport_id", "integer", "OurAirports id (joins runways.airport_id)"),
        Column("ident", "string", "OurAirports identifier, usually the ICAO code (e.g. WIII)"),
        Column("type", "string", "large_airport, medium_airport, small_airport, heliport, seaplane_base, balloonport or closed"),
        Column("name", "string", "Airport name"),
        Column("latitude", "number", "Latitude"),
        Column("longitude", "number", "Longitude"),
        Column("elevation_m", "number", "Elevation in metres"),
        Column("continent", "string", "Continent code (AS, EU, NA, SA, AF, OC, AN)"),
        Column("country_code", "string", "ISO 3166-1 alpha-2 country code"),
        Column("country", "string", "Country name"),
        Column("region_code", "string", "ISO 3166-2 region code (e.g. ID-JK)"),
        Column("region", "string", "Region name (a province in Indonesia)"),
        Column("municipality", "string", "City or town served"),
        Column("scheduled_service", "boolean", "Has scheduled airline service"),
        Column("icao_code", "string", "ICAO code"),
        Column("iata_code", "string", "IATA code (e.g. CGK)"),
    ],
)

RUNWAYS = Table(
    name="runways",
    kind="history",
    description="Every runway: length and width in metres, surface, lighting, whether it is closed, and its end identifiers.",
    key=("runway_id",),
    min_rows=35_000,
    max_shrink=0.03,
    columns=[
        Column("runway_id", "integer", "OurAirports runway id"),
        Column("airport_id", "integer", "Airport (joins airports.airport_id)"),
        Column("length_m", "number", "Length in metres"),
        Column("width_m", "number", "Width in metres"),
        Column("surface", "string", "Surface code as entered, e.g. ASP (asphalt), CON (concrete), GRS (grass)"),
        Column("paved", "boolean", "Hard surface (asphalt, concrete, bitumen or similar)"),
        Column("lighted", "boolean", "Runway has lights"),
        Column("closed", "boolean", "Runway is closed"),
        Column("ends", "string", "Runway end identifiers, e.g. 07L/25R"),
    ],
)

COUNTRIES = Table(
    name="countries",
    kind="derived",
    description="One row per country: airports by type, airports with scheduled service, paved runways and the longest runway.",
    key=("country_code",),
    min_rows=0,
    columns=[
        Column("country_code", "string", "ISO alpha-2 code"),
        Column("country", "string", "Country"),
        Column("large_airports", "integer", "Large airports (major hubs)"),
        Column("medium_airports", "integer", "Medium airports"),
        Column("small_airports", "integer", "Small airports and airstrips"),
        Column("heliports", "integer", "Heliports"),
        Column("seaplane_bases", "integer", "Seaplane bases"),
        Column("scheduled_airports", "integer", "Open airports with scheduled airline service"),
        Column("paved_runway_share_pct", "number", "Share of open runways with a hard surface (%)"),
        Column("longest_runway_m", "number", "Longest open runway (m)"),
        Column("longest_runway_airport", "string", "Airport with that runway"),
    ],
)

TABLES = [AIRPORTS, RUNWAYS, COUNTRIES]

# ---------- download and parsing ----------


def make_session():
    return base_session()


def download(session, name):
    resp = session.get(BASE + f"{name}.csv", timeout=300)
    resp.raise_for_status()
    return pd.read_csv(io.BytesIO(resp.content), keep_default_na=False, na_values=[""], low_memory=False)


def tidy_airports(raw, countries, regions):
    names = dict(zip(countries["code"], countries["name"]))
    region_names = dict(zip(regions["code"], regions["name"]))
    df = pd.DataFrame({
        "airport_id": raw["id"], "ident": raw["ident"], "type": raw["type"], "name": raw["name"],
        "latitude": raw["latitude_deg"].round(6), "longitude": raw["longitude_deg"].round(6),
        "elevation_m": (pd.to_numeric(raw["elevation_ft"], errors="coerce") * FT).round(1),
        "continent": raw["continent"], "country_code": raw["iso_country"], "country": raw["iso_country"].map(names),
        "region_code": raw["iso_region"], "region": raw["iso_region"].map(region_names), "municipality": raw["municipality"],
        "scheduled_service": raw["scheduled_service"].eq("yes"), "icao_code": raw["icao_code"], "iata_code": raw["iata_code"],
    })
    return df.sort_values("airport_id").reset_index(drop=True)


def tidy_runways(raw):
    surface = raw["surface"].astype("string").str.strip()
    ends = raw["le_ident"].fillna("").astype(str) + "/" + raw["he_ident"].fillna("").astype(str)
    df = pd.DataFrame({
        "runway_id": raw["id"], "airport_id": raw["airport_ref"],
        "length_m": (pd.to_numeric(raw["length_ft"], errors="coerce") * FT).round(0),
        "width_m": (pd.to_numeric(raw["width_ft"], errors="coerce") * FT).round(0), "surface": surface,
        "paved": surface.str.upper().str.startswith(PAVED).fillna(False),
        "lighted": raw["lighted"].eq(1), "closed": raw["closed"].eq(1), "ends": ends.str.strip("/").replace("", None),
    })
    return df.sort_values("runway_id").reset_index(drop=True)


def make_fetchers(_, snapshot_date):
    session = make_session()
    cache = {}

    def get(name):
        if name not in cache:
            cache[name] = download(session, name)
        return cache[name]

    return {
        "airports": lambda previous: tidy_airports(get("airports"), get("countries"), get("regions")),
        "runways": lambda previous: tidy_runways(get("runways")),
    }


# ---------- derived ----------


def countries(airports, runways):
    if airports is None or airports.empty:
        return pd.DataFrame(columns=COUNTRIES.column_names)
    a = airports[airports["type"] != "closed"]
    types = ["large_airport", "medium_airport", "small_airport", "heliport", "seaplane_base"]
    by_type = a.pivot_table(index="country_code", columns="type", values="airport_id", aggfunc="count")
    by_type = by_type.reindex(columns=types).fillna(0)  # a type absent everywhere still gets a column of zeros
    out = pd.DataFrame({
        "country": a.groupby("country_code")["country"].first(),
        **{col: by_type[t].astype(int) for col, t in (("large_airports", "large_airport"), ("medium_airports", "medium_airport"),
                                                              ("small_airports", "small_airport"), ("heliports", "heliport"),
                                                              ("seaplane_bases", "seaplane_base"))},
        "scheduled_airports": a[a["scheduled_service"]].groupby("country_code").size(),
    })
    out["scheduled_airports"] = out["scheduled_airports"].fillna(0).astype(int)
    if runways is not None and not runways.empty:
        r = runways[~runways["closed"]].merge(a[["airport_id", "country_code", "name"]], on="airport_id")
        out["paved_runway_share_pct"] = (r.groupby("country_code")["paved"].mean() * 100).round(1)
        longest = r.dropna(subset=["length_m"]).sort_values("length_m").groupby("country_code").tail(1).set_index("country_code")
        out["longest_runway_m"] = longest["length_m"]
        out["longest_runway_airport"] = longest["name"]
    return out.reset_index().rename(columns={"index": "country_code"}).reindex(columns=COUNTRIES.column_names) \
        .sort_values("scheduled_airports", ascending=False).reset_index(drop=True)


def derive(frames):
    return {"countries": countries(frames.get("airports"), frames.get("runways"))}


# ---------- description ----------


def overview(frames):
    a, r = (frames or {}).get("airports"), (frames or {}).get("runways")
    if a is None or a.empty:
        return "(computed when the dataset is built)"
    c = countries(a, r)
    t = a["type"].value_counts()
    lines = [f"**{len(a):,} places** in {a['country_code'].nunique()} countries: {t.get('large_airport', 0):,} large and "
             f"{t.get('medium_airport', 0):,} medium airports, {t.get('small_airport', 0):,} small airports and airstrips, "
             f"{t.get('heliport', 0):,} heliports; {len(r) if r is not None else 0:,} runways.", "",
             "| Country | Airports with scheduled flights | Large | Medium | Small | Longest runway |", "|---|---|---|---|---|---|"]
    for x in c.head(10).itertuples():
        lr = f"{x.longest_runway_m:,.0f} m" if pd.notna(x.longest_runway_m) else "–"
        lines.append(f"| {x.country} | {x.scheduled_airports:,} | {x.large_airports} | {x.medium_airports} | {x.small_airports:,} | {lr} |")
    idn = c[c["country_code"] == "ID"]
    if len(idn):
        x = idn.iloc[0]
        lines += ["", f"Indonesia: {x['scheduled_airports']} airports with scheduled flights, {x['small_airports']:,} small "
                      f"airports and airstrips, {x['paved_runway_share_pct']:.0f}% of runways paved."]
    return "\n".join(lines)


def describe(snapshot_date, tables_written, frames=None):
    return "\n".join([
        "**Every airport in the world, with its runways**: more than 80,000 airports, airstrips, heliports and seaplane "
        "bases from OurAirports, with type, location, region, ICAO and IATA codes and scheduled-service flag, plus "
        "every runway's length, width, surface and lighting, and a per-country summary.",
        "",
        "## Why this dataset",
        "",
        "- **Aviation and logistics analysis**: map airport networks, find which regions lack paved runways, or size "
        "the market for regional aviation.",
        "- **Clean and joinable**: metric units, country and region names already joined (Indonesia's provinces "
        "included), and boolean flags instead of yes/no text.",
        "- **Geospatial practice**: real coordinates for distance, coverage and nearest-airport problems.",
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
        "- **Volunteer-maintained**: OurAirports is edited by volunteers. Coverage of large airports is very good; "
        "small airstrips and heliports are less complete in some countries.",
        "- **Types**: 'large_airport' roughly means a major hub, 'medium' a regional airport with scheduled service, "
        "'small' a general-aviation field; 'closed' places are kept for history.",
        "- **Paved** is inferred from the surface code (asphalt, concrete, bitumen and similar).",
        "",
        "## Updates",
        "",
        f"Rebuilt weekly from OurAirports' nightly files. Last update: {snapshot_date:%Y-%m-%d} (UTC).",
        "",
        "## Source and license",
        "",
        "OurAirports (https://ourairports.com), data files at https://github.com/davidmegginson/ourairports-data. "
        "OurAirports releases its data to the public domain, with no guarantee of accuracy; it is not for navigation. "
        "Not affiliated with OurAirports.",
    ])


SPEC = DatasetSpec(
    name="airports",
    slug="world-airports-runways-ourairports",
    title="World Airports & Runways (OurAirports)",
    subtitle="Every airport, airstrip and heliport with runways, codes and regions, weekly",
    license="other",
    keywords=["geography", "cities and urban areas", "international relations", "tabular", "data visualization"],
    tables=TABLES,
    sources="OurAirports (https://ourairports.com), public domain data files at "
            "https://github.com/davidmegginson/ourairports-data. Built weekly by https://github.com/daniel766hi/kaggle-compe",
    make_fetchers=make_fetchers,
    derive=derive,
    describe=describe,
    cover=ASSETS / "airports-cover.png",
    update_frequency="weekly",
    run_weekday=2,  # Wednesday
)
