"""Indonesia's modern retail network: every convenience store and supermarket mapped in OpenStreetMap, by chain.

Source: OpenStreetMap (https://www.openstreetmap.org), via the Overpass API, under the Open Database License
(ODbL) 1.0. Stores are queried one province at a time (38 provinces) and matched to chains (Indomaret, Alfamart,
Alfamidi, Lawson, Circle K, Superindo, ...) by their brand tag, or failing that, their name.

OpenStreetMap is mapped by volunteers: coverage is good in big cities and patchy elsewhere, so counts are a lower
bound and grow as mapping improves, not only as stores open. Each weekly snapshot of the counts is kept so both
effects can be followed.
"""

import logging
import re
import time
from pathlib import Path

import pandas as pd

from ..http import make_session as base_session
from ..schema import Column, DatasetSpec, Table, files_markdown

log = logging.getLogger(__name__)

ASSETS = Path(__file__).resolve().parents[2] / "assets"
# Public Overpass instances, tried in turn: the main one is often overloaded (HTTP 502/504).
OVERPASS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
PAUSE_S = 8  # between provinces: Overpass is a shared, volunteer-run service

PROVINCES = {  # ISO 3166-2 code -> province
    "ID-AC": "Aceh", "ID-SU": "Sumatera Utara", "ID-SB": "Sumatera Barat", "ID-RI": "Riau", "ID-KR": "Kepulauan Riau",
    "ID-JA": "Jambi", "ID-SS": "Sumatera Selatan", "ID-BB": "Kepulauan Bangka Belitung", "ID-BE": "Bengkulu",
    "ID-LA": "Lampung", "ID-JK": "DKI Jakarta", "ID-BT": "Banten", "ID-JB": "Jawa Barat", "ID-JT": "Jawa Tengah",
    "ID-YO": "DI Yogyakarta", "ID-JI": "Jawa Timur", "ID-BA": "Bali", "ID-NB": "Nusa Tenggara Barat",
    "ID-NT": "Nusa Tenggara Timur", "ID-KB": "Kalimantan Barat", "ID-KT": "Kalimantan Tengah",
    "ID-KS": "Kalimantan Selatan", "ID-KI": "Kalimantan Timur", "ID-KU": "Kalimantan Utara", "ID-SA": "Sulawesi Utara",
    "ID-GO": "Gorontalo", "ID-ST": "Sulawesi Tengah", "ID-SR": "Sulawesi Barat", "ID-SN": "Sulawesi Selatan",
    "ID-SG": "Sulawesi Tenggara", "ID-MA": "Maluku", "ID-MU": "Maluku Utara", "ID-PA": "Papua", "ID-PB": "Papua Barat",
    "ID-PD": "Papua Barat Daya", "ID-PS": "Papua Selatan", "ID-PT": "Papua Tengah", "ID-PE": "Papua Pegunungan",
}

# Chain -> pattern matched against the brand tag, then the name (case-insensitive). Order matters: Alfamidi before
# Alfamart, Indomaret Fresh/Point and Super Indo are distinct chains.
CHAINS = [
    ("Alfamidi", r"alfa ?midi"), ("Alfa Express", r"alfa ?express"), ("Alfamart", r"alfa ?mart"),
    ("Indomaret Fresh", r"indomaret fresh"), ("Indomaret Point", r"indomaret point"), ("Indomaret", r"indo ?maret"),
    ("Lawson", r"\blawson"), ("FamilyMart", r"family ?mart"), ("Circle K", r"circle ?k\b"), ("Yomart", r"\byomart"),
    ("Superindo", r"super ?indo"), ("Hypermart", r"hypermart"), ("Transmart", r"trans ?mart|carrefour"),
    ("Lotte Mart", r"lotte ?mart"), ("Hero", r"^hero\b"), ("Giant", r"^giant\b"), ("Ranch Market", r"ranch market"),
    ("Hari Hari", r"hari ?hari"), ("Tip Top", r"tip ?top"), ("Toko Merah", r"toko merah"),
]
CHAINS = [(c, re.compile(p, re.I)) for c, p in CHAINS]

STORES = Table(
    name="stores",
    kind="history",  # the current OSM map, rebuilt every run
    description="Every convenience store and supermarket in Indonesia mapped in OpenStreetMap: chain, name, province and location.",
    key=("osm_type", "osm_id"),
    min_rows=10_000,
    max_shrink=0.10,  # mappers merge and delete duplicates; a big drop means a failed province query
    columns=[
        Column("osm_type", "string", "OpenStreetMap element type: node, way or relation"),
        Column("osm_id", "integer", "OpenStreetMap id (with osm_type, e.g. openstreetmap.org/node/123)"),
        Column("province", "string", "Province the store is in"),
        Column("shop", "string", "OSM shop type: convenience or supermarket"),
        Column("chain", "string", "Chain, e.g. Indomaret, Alfamart, Superindo; 'Independent' when no chain matches"),
        Column("name", "string", "Store name as mapped"),
        Column("brand_tag", "string", "OSM brand tag, if mapped"),
        Column("city", "string", "addr:city tag, if mapped (often empty)"),
        Column("opening_hours", "string", "OSM opening_hours tag, e.g. '24/7', if mapped"),
        Column("latitude", "number", "Latitude (store point, or centre of a mapped building)"),
        Column("longitude", "number", "Longitude"),
    ],
)

COUNTS = Table(
    name="chain_counts_snapshots",
    kind="snapshot",
    description="Each week: stores per chain and province as mapped in OpenStreetMap, to follow growth over time.",
    key=("snapshot_date", "province", "chain"),
    min_rows=100,
    columns=[
        Column("snapshot_date", "datetime", "Date of the weekly update (UTC)"),
        Column("province", "string", "Province"),
        Column("chain", "string", "Chain, or 'Independent'"),
        Column("stores", "integer", "Stores mapped in OpenStreetMap on that date"),
    ],
)

PROVINCE_SUMMARY = Table(
    name="province_summary",
    kind="derived",
    description="One row per province: mapped stores, the two big chains, other chains, independents and the leading chain.",
    key=("province",),
    min_rows=0,
    columns=[
        Column("province", "string", "Province"),
        Column("stores", "integer", "Convenience stores and supermarkets mapped"),
        Column("indomaret", "integer", "Indomaret stores (incl. Indomaret Fresh and Point)"),
        Column("alfamart", "integer", "Alfamart group stores (Alfamart, Alfamidi, Alfa Express)"),
        Column("other_chains", "integer", "Stores of other chains"),
        Column("independent", "integer", "Stores matched to no chain"),
        Column("indomaret_vs_alfamart", "number", "Indomaret stores per Alfamart-group store (>1: Indomaret leads)"),
        Column("leading_chain", "string", "Chain with the most mapped stores in the province"),
    ],
)

TABLES = [STORES, COUNTS, PROVINCE_SUMMARY]

# ---------- download ----------


def make_session():
    return base_session()


def query(iso):
    return (f'[out:json][timeout:240];area["ISO3166-2"="{iso}"]["boundary"="administrative"]->.a;'
            'nwr(area.a)["shop"~"^(convenience|supermarket)$"];out center tags;')


def overpass(session, iso, attempts=6, sleep=None):
    """Elements for one province, rotating through the Overpass instances on errors."""
    sleep = sleep or time.sleep
    for attempt in range(attempts):
        url = OVERPASS[attempt % len(OVERPASS)]
        try:
            resp = session.post(url, data={"data": query(iso)}, timeout=200,
                                headers={"User-Agent": "kaggle-compe-dataset-builder (github.com/daniel766hi/kaggle-compe)"})
            if resp.status_code in (429, 502, 503, 504):
                raise RuntimeError(f"Overpass busy ({resp.status_code})")
            resp.raise_for_status()
            data = resp.json()
            if "remark" in data and "runtime error" in str(data["remark"]).lower():
                raise RuntimeError(f"Overpass query error: {data['remark'][:120]}")  # e.g. timed out on the server
            if not data.get("elements"):
                # Every province has mapped shops; an empty answer means an instance without that area indexed.
                raise RuntimeError("empty answer")
            return data["elements"]
        except Exception as exc:  # noqa: BLE001 - retried on the next instance, then raised
            if attempt == attempts - 1:
                raise
            log.warning("Overpass %s failed on %s (%s); trying the next instance", iso, url.split("/")[2], exc)
            sleep(20 * (attempt // len(OVERPASS) + 1))
    return []


def chain_of(brand, name):
    for text in (brand, name):
        if text:
            for chain, pattern in CHAINS:
                if pattern.search(text):
                    return chain
    return "Independent"


def tidy(elements, province):
    rows = []
    for e in elements:
        tags = e.get("tags", {})
        lat = e.get("lat", (e.get("center") or {}).get("lat"))
        lon = e.get("lon", (e.get("center") or {}).get("lon"))
        if lat is None or lon is None:
            continue
        brand, name = tags.get("brand"), tags.get("name")
        rows.append({"osm_type": e["type"], "osm_id": e["id"], "province": province, "shop": tags.get("shop"),
                     "chain": chain_of(brand, name), "name": name, "brand_tag": brand, "city": tags.get("addr:city"),
                     "opening_hours": tags.get("opening_hours"), "latitude": round(lat, 6), "longitude": round(lon, 6)})
    return rows


def fetch_stores(session, pause_s=PAUSE_S, sleep=None):
    """All provinces; a province that fails is retried in a second pass, and the run fails if any still fails,
    so a published snapshot never silently misses a province."""
    sleep = sleep or time.sleep
    rows, failed = [], []
    for attempt in (1, 2):
        todo = list(PROVINCES.items()) if attempt == 1 else failed
        failed = []
        for iso, province in todo:
            try:
                elements = overpass(session, iso, sleep=sleep)
            except Exception as exc:  # noqa: BLE001 - retried in the second pass
                log.warning("Overpass %s (%s) failed: %s", province, iso, exc)
                failed.append((iso, province))
                continue
            if not elements:
                log.warning("No stores returned for %s (%s)", province, iso)
            rows += tidy(elements, province)
            log.info("Overpass %s: %d stores", province, len(elements))
            sleep(pause_s)
        if not failed:
            break
        log.warning("Retrying %d provinces: %s", len(failed), [p for _, p in failed])
        sleep(120)
    if failed:
        raise RuntimeError(f"Overpass failed for {len(failed)} provinces: {[p for _, p in failed]}")
    df = pd.DataFrame(rows, columns=STORES.column_names)
    # A store on a province border can come back for both provinces; keep the first.
    return df.drop_duplicates(["osm_type", "osm_id"]).sort_values(["province", "chain", "osm_id"]).reset_index(drop=True)


def counts(stores, snapshot_date):
    c = stores.groupby(["province", "chain"]).size().rename("stores").reset_index()
    return c.assign(snapshot_date=pd.Timestamp(snapshot_date))[COUNTS.column_names]


def make_fetchers(_, snapshot_date):
    session = make_session()
    cache = {}

    def stores():
        # Fetch once: if it fails, the counts table must not start the whole download again.
        if "s" not in cache:
            try:
                cache["s"] = fetch_stores(session)
            except Exception as exc:  # noqa: BLE001 - re-raised for both tables
                cache["s"] = exc
        if isinstance(cache["s"], Exception):
            raise cache["s"]
        return cache["s"]

    return {"stores": lambda previous: stores(), "chain_counts_snapshots": lambda previous: counts(stores(), snapshot_date)}


# ---------- derived ----------

INDOMARET = {"Indomaret", "Indomaret Fresh", "Indomaret Point"}
ALFA = {"Alfamart", "Alfamidi", "Alfa Express"}


def province_summary(stores):
    if stores is None or stores.empty:
        return pd.DataFrame(columns=PROVINCE_SUMMARY.column_names)
    rows = []
    for province, d in stores.groupby("province"):
        chains = d.loc[d["chain"] != "Independent", "chain"].value_counts()
        ind, alfa = int(d["chain"].isin(INDOMARET).sum()), int(d["chain"].isin(ALFA).sum())
        rows.append({"province": province, "stores": len(d), "indomaret": ind, "alfamart": alfa,
                     "other_chains": int((~d["chain"].isin(INDOMARET | ALFA | {"Independent"})).sum()),
                     "independent": int((d["chain"] == "Independent").sum()),
                     "indomaret_vs_alfamart": round(ind / alfa, 2) if alfa else None,
                     "leading_chain": chains.index[0] if len(chains) else None})
    return pd.DataFrame(rows).sort_values("stores", ascending=False)[PROVINCE_SUMMARY.column_names].reset_index(drop=True)


def derive(frames):
    return {"province_summary": province_summary(frames.get("stores"))}


# ---------- description ----------


def overview(frames):
    stores = (frames or {}).get("stores")
    if stores is None or stores.empty:
        return "(computed when the dataset is built)"
    chains = stores["chain"].value_counts()
    lines = [f"**{len(stores):,} stores** mapped in {stores['province'].nunique()} provinces "
             f"({(stores['shop'] == 'convenience').sum():,} convenience stores, {(stores['shop'] == 'supermarket').sum():,} supermarkets).",
             "", "| Chain | Stores mapped |", "|---|---|"]
    lines += [f"| {c} | {n:,} |" for c, n in chains.head(12).items()]
    return "\n".join(lines)


def describe(snapshot_date, tables_written, frames=None):
    return "\n".join([
        "**Where Indonesia shops**: every convenience store and supermarket mapped in OpenStreetMap across all 38 "
        "provinces, matched to chains (Indomaret, Alfamart, Alfamidi, Lawson, Circle K, Superindo, Hypermart, ...), "
        "with location, province and opening hours, plus weekly counts per chain and province.",
        "",
        "## Why this dataset",
        "",
        "- **FMCG and retail analysis**: compare the two minimarket giants province by province, find white space "
        "for distribution, or map retail density against population and income.",
        "- **Geospatial practice**: real coordinates for clustering, nearest-store distances, catchment areas and "
        "logistics routing.",
        "- **Growth over time**: each weekly snapshot of the counts is kept, so you can follow how the mapped network "
        "changes.",
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
        "- **A map, not a census**: OpenStreetMap is built by volunteers. Big cities are well mapped, many districts "
        "are not, so every count is a lower bound and differences between provinces partly reflect mapping effort. "
        "Use the chain shares within a province more than raw totals across provinces.",
        "- **Chains** are matched by the brand tag, then the store name; small chains and family shops count as "
        "'Independent'. Indomaret Fresh/Point and Alfamidi/Alfa Express are kept separate from the main brands.",
        "- **Growth** in `chain_counts_snapshots` mixes new stores with newly mapped old stores.",
        "",
        "## Updates",
        "",
        f"Rebuilt weekly from OpenStreetMap. Last update: {snapshot_date:%Y-%m-%d} (UTC).",
        "",
        "## Source and license",
        "",
        "© OpenStreetMap contributors (https://www.openstreetmap.org/copyright). The data is available under the Open "
        "Database License (ODbL) 1.0; this dataset is a derived database shared under the same license. Attribute "
        "'© OpenStreetMap contributors' when you use it, and share databases you derive from it under the ODbL.",
    ])


SPEC = DatasetSpec(
    name="idn-retail",
    slug="indonesia-minimarket-network-indomaret-alfamart",
    title="Indonesia Minimarkets: Indomaret vs Alfamart Map",
    subtitle="Every convenience store and supermarket in OpenStreetMap, 38 provinces, weekly",
    license="ODbL-1.0",
    keywords=["asia", "geography", "cities and urban areas", "economics", "tabular"],
    tables=TABLES,
    sources="© OpenStreetMap contributors, via the Overpass API (https://overpass-api.de), ODbL 1.0. "
            "Built weekly by https://github.com/daniel766hi/kaggle-compe",
    make_fetchers=make_fetchers,
    derive=derive,
    describe=describe,
    cover=ASSETS / "idn-retail-cover.png",
    update_frequency="weekly",
    run_weekday=5,  # Saturday
)
