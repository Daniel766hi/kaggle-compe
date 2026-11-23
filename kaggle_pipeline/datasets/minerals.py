"""World mineral production and reserves by country: the USGS Mineral Commodity Summaries data release.

Source: U.S. Geological Survey, Mineral Commodity Summaries (MCS) data release on ScienceBase
(https://www.sciencebase.gov), a U.S. Government work in the public domain. Each yearly edition (published around
February, revised during the year) has world mine, refinery and smelter production, capacity and reserves by country
for about 90 mineral commodities, for the two latest years. Each run takes the newest edition found and keeps the
rows of earlier editions it already holds, so the history grows by one edition a year.
"""

import io
import logging
import re
from pathlib import Path

import pandas as pd

from ..http import make_session as base_session
from ..schema import Column, DatasetSpec, Table, files_markdown

log = logging.getLogger(__name__)

ASSETS = Path(__file__).resolve().parents[2] / "assets"
CATALOG = "https://www.sciencebase.gov/catalog"
PARENT = "5c8c03e4e4b0938824529f7d"  # USGS Mineral Commodity Summaries data releases
FALLBACK_ITEM = "696a75d5d4be0228872d3bf8"  # MCS 2026 data release

PRODUCTION = Table(
    name="world_production",
    kind="incremental",  # one edition per year is added; earlier editions are kept
    description="Per edition, commodity, country and year: mine/refinery production, capacity or reserves as published by USGS.",
    key=("edition", "commodity", "section", "country", "statistic", "detail", "year"),
    min_rows=2_500,
    columns=[
        Column("edition", "integer", "MCS edition year (e.g. 2026; it reports the two previous years)"),
        Column("commodity", "string", "Commodity, e.g. Nickel, Tin, Bauxite, Copper"),
        Column("section", "string", "Table it comes from, e.g. 'World Mine Production and Reserves'"),
        Column("country", "string", "Country, 'Other countries' or 'World total'"),
        Column("statistic", "string", "Production, Reserves or Capacity"),
        Column("detail", "string", "What exactly is measured, e.g. 'Mine production', 'Refinery production'"),
        Column("unit", "string", "Unit, e.g. metric tons, thousand metric tons, kilograms"),
        Column("year", "integer", "Year the value refers to"),
        Column("value", "number", "Value as a number; '—' (zero) is 0; withheld, ranges and words are empty"),
        Column("value_text", "string", "Value as published (keeps W = withheld, XX, ranges, 'Large' and the like)"),
        Column("is_estimate", "boolean", "USGS marks the value as estimated"),
        Column("is_critical", "boolean", "On the 2025 U.S. critical minerals list"),
        Column("notes", "string", "USGS notes for the row (rounding, revisions, definitions)"),
    ],
)

LEADERS = Table(
    name="commodity_leaders",
    kind="derived",
    description="Per commodity and measure, latest edition and year: world total, leading country and Indonesia's rank and share.",
    key=("commodity", "section", "statistic", "detail"),
    min_rows=0,
    columns=[
        Column("commodity", "string", "Commodity"),
        Column("section", "string", "USGS table"),
        Column("statistic", "string", "Production, Reserves or Capacity"),
        Column("detail", "string", "What is measured"),
        Column("unit", "string", "Unit"),
        Column("year", "integer", "Year of the values"),
        Column("world_total", "number", "World total as published (empty if USGS gives none)"),
        Column("top_country", "string", "Country with the largest value"),
        Column("top_share_pct", "number", "Its share of the world total (%)"),
        Column("top3_share_pct", "number", "Share of the three largest countries (%)"),
        Column("indonesia_value", "number", "Indonesia's value (empty if not listed)"),
        Column("indonesia_share_pct", "number", "Indonesia's share of the world total (%)"),
        Column("indonesia_rank", "integer", "Indonesia's rank among listed countries (1 = largest)"),
        Column("is_critical", "boolean", "On the 2025 U.S. critical minerals list"),
    ],
)

TABLES = [PRODUCTION, LEADERS]

# ---------- download and parsing ----------


def make_session():
    return base_session()


def latest_item(session):
    """(edition year, item id) of the newest MCS data release, or the known 2026 one if the catalog cannot be read."""
    try:
        resp = session.get(f"{CATALOG}/items", params={"parentId": PARENT, "format": "json", "fields": "title", "max": 200},
                           timeout=60)
        resp.raise_for_status()
        found = []
        for item in resp.json().get("items", []):
            m = re.match(r"Mineral Commodity Summaries (\d{4}) Data Release$", item.get("title", "").strip())
            if m:
                found.append((int(m.group(1)), item["id"]))
        if found:
            return max(found)
        log.warning("No MCS data release listed under %s; using the 2026 release", PARENT)
    except Exception as exc:  # noqa: BLE001 - the catalog listing is only a pointer
        log.warning("ScienceBase listing failed (%s); using the 2026 release", exc)
    return 2026, FALLBACK_ITEM


def download(session):
    edition, item = latest_item(session)
    resp = session.get(f"{CATALOG}/item/{item}", params={"format": "json"}, timeout=60)
    resp.raise_for_status()
    files = [f for f in resp.json().get("files", []) if re.search(r"Commodities_Data\.csv$", f.get("name", ""))]
    if not files:
        raise RuntimeError(f"No *_Commodities_Data.csv in ScienceBase item {item}")
    data = session.get(files[0]["url"], timeout=300)
    data.raise_for_status()
    log.info("USGS MCS %d: %s (%d bytes)", edition, files[0]["name"], len(data.content))
    return edition, data.content


def number(text):
    t = str(text).strip()
    if t in ("—", "—", "-"):
        return 0.0  # USGS uses an em dash for zero
    t = t.replace(",", "")
    return float(t) if re.fullmatch(r"-?\d+(\.\d+)?", t) else None


def parse(content, edition):
    raw = pd.read_csv(io.BytesIO(content), encoding="cp1252", dtype=str)
    w = raw[raw["Section"].str.startswith("World", na=False)].copy()
    w["Section"] = w["Section"].str.rstrip(":").str.strip()
    out = pd.DataFrame({
        "edition": edition, "commodity": w["Commodity"].str.strip(), "section": w["Section"],
        "country": w["Country"].str.strip(), "statistic": w["Statistics"].str.strip(),
        # World totals are labelled e.g. "Mine production: rounded"; drop the suffix so they match the country rows.
        "detail": w["Statistics_detail"].str.strip().str.replace(r"[:,]\s*rounded$", "", regex=True).str.strip(),
        "unit": w["Unit"].str.strip(),
        "year": pd.to_numeric(w["Year"], errors="coerce"), "value": w["Value"].map(number), "value_text": w["Value"].str.strip(),
        "is_estimate": w["Notes"].fillna("").str.contains(r"\bEstimated\b", regex=True),
        "is_critical": w["Is critical mineral 2025"].fillna("").str.strip().eq("Yes"), "notes": w["Notes"].str.strip(),
    })
    out = out.dropna(subset=["year"]).astype({"year": int})
    dupes = out.duplicated(PRODUCTION.key, keep="first")
    if dupes.any():
        log.warning("Dropping %d repeated rows", int(dupes.sum()))
    return out[~dupes][PRODUCTION.column_names].reset_index(drop=True)


def make_fetchers(_, snapshot_date):
    session = make_session()

    def fetch(previous):
        edition, content = download(session)
        return parse(content, edition)

    return {"world_production": fetch}


# ---------- derived ----------


def leaders(prod):
    if prod is None or prod.empty:
        return pd.DataFrame(columns=LEADERS.column_names)
    p = prod[prod["edition"] == prod["edition"].max()]
    rows = []
    for key, d in p.groupby(["commodity", "section", "statistic", "detail"]):
        d = d[d["year"] == d["year"].max()]
        world = d.loc[d["country"].str.startswith("World"), "value"]
        world_total = world.iloc[0] if len(world) and pd.notna(world.iloc[0]) else None
        c = d[~d["country"].str.startswith(("World", "Other countries"))].dropna(subset=["value"])
        c = c[c["value"] > 0].sort_values("value", ascending=False)
        if c.empty:
            continue
        share = lambda v: round(100 * v / world_total, 1) if world_total else None
        idn = c[c["country"] == "Indonesia"]
        rank = int((c["value"] > idn["value"].iloc[0]).sum() + 1) if len(idn) else None
        rows.append({"commodity": key[0], "section": key[1], "statistic": key[2], "detail": key[3],
                     "unit": d["unit"].iloc[0], "year": int(d["year"].iloc[0]), "world_total": world_total,
                     "top_country": c["country"].iloc[0], "top_share_pct": share(c["value"].iloc[0]),
                     "top3_share_pct": share(c["value"].head(3).sum()),
                     "indonesia_value": idn["value"].iloc[0] if len(idn) else None,
                     "indonesia_share_pct": share(idn["value"].iloc[0]) if len(idn) else None,
                     "indonesia_rank": rank, "is_critical": bool(d["is_critical"].any())})
    return pd.DataFrame(rows, columns=LEADERS.column_names).sort_values(["commodity", "statistic"]).reset_index(drop=True)


def derive(frames):
    return {"commodity_leaders": leaders(frames.get("world_production"))}


# ---------- description ----------


def overview(frames):
    prod = (frames or {}).get("world_production")
    lead = leaders(prod)
    if lead.empty:
        return "(computed when the dataset is built)"
    ed = int(prod["edition"].max())
    idn = lead[(lead["indonesia_rank"].notna()) & (lead["statistic"] == "Production") & (lead["indonesia_share_pct"].notna())]
    idn = idn.sort_values("indonesia_share_pct", ascending=False).head(10)
    lines = [f"Edition {ed}: {prod[prod['edition'] == ed]['commodity'].nunique()} commodities, "
             f"{prod[prod['edition'] == ed]['country'].nunique()} countries; {len(prod):,} rows in all editions.", "",
             "Where Indonesia ranks in world production:", "",
             "| Commodity | Measure | Year | Indonesia's share | Rank | World leader |", "|---|---|---|---|---|---|"]
    for r in idn.itertuples():
        lines.append(f"| {r.commodity} | {r.detail} | {r.year} | {r.indonesia_share_pct:.1f}% | {int(r.indonesia_rank)} | {r.top_country} |")
    return "\n".join(lines)


def describe(snapshot_date, tables_written, frames=None):
    return "\n".join([
        "**Who mines and refines the world's minerals**: production, capacity and reserves by country for about 90 "
        "mineral commodities (nickel, tin, copper, bauxite, lithium, cobalt, rare earths, gold and more), from the U.S. "
        "Geological Survey's Mineral Commodity Summaries, with a summary of the world leader and Indonesia's position "
        "for each.",
        "",
        "## Why this dataset",
        "",
        "- **Mining and supply-chain analysis**: see how concentrated each mineral is, who holds the reserves, and how "
        "fast production shifts, e.g. Indonesia's rise in nickel.",
        "- **Clean numbers with nothing lost**: values parsed to numbers, with the published text kept for withheld "
        "(W), not applicable (XX), ranges and qualitative reserves.",
        "- **Grows each year**: every new USGS edition is added and earlier editions are kept.",
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
        "- **Units differ by commodity and row** (metric tons, thousand metric tons, kilograms, carats); compare "
        "within one commodity and detail.",
        "- **Production types differ**: mine production, refinery or smelter production and capacity are separate "
        "rows; do not add them together.",
        "- **'—' means zero; W means withheld** to protect company data; XX means not applicable. World totals are "
        "rounded by USGS, so country values need not add up to them exactly.",
        "- **Latest year values are estimates** (`is_estimate`) and are revised in the next edition.",
        "",
        "## Updates",
        "",
        f"Checked monthly for a new or revised USGS edition. Last update: {snapshot_date:%Y-%m-%d} (UTC).",
        "",
        "## Source and terms",
        "",
        "U.S. Geological Survey, Mineral Commodity Summaries data release (https://www.usgs.gov/centers/national-"
        "minerals-information-center/mineral-commodity-summaries), via ScienceBase. A U.S. Government work in the "
        "public domain; cite the USGS when you use it. Not affiliated with the USGS.",
    ])


SPEC = DatasetSpec(
    name="minerals",
    slug="world-mineral-production-reserves-usgs",
    title="World Mineral Production & Reserves (USGS)",
    subtitle="Mine and refinery output, capacity and reserves by country for 90 minerals",
    license="CC0-1.0",
    keywords=["economics", "geography", "international relations", "environment", "tabular"],
    tables=TABLES,
    sources="U.S. Geological Survey, Mineral Commodity Summaries data release (ScienceBase), public domain. "
            "Built monthly by https://github.com/daniel766hi/kaggle-compe",
    make_fetchers=make_fetchers,
    derive=derive,
    describe=describe,
    cover=ASSETS / "minerals-cover.png",
    update_frequency="monthly",
    run_days=(7,),
)
