"""World commodity prices: the World Bank's monthly "Pink Sheet", 71 commodities since 1960, tidied and enriched.

Source: World Bank Commodity Price Data (The Pink Sheet), https://www.worldbank.org/en/research/commodity-markets.
The workbook moves to a new address every year, so each run reads the current link from the Commodity Markets page
and falls back to the last known address if the page cannot be read. Released early each month (usually the
2nd-3rd business day) with the previous month's averages; recent months can be revised.
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
PAGE = "https://www.worldbank.org/en/research/commodity-markets"
FALLBACK = ("https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/"
            "CMO-Historical-Data-Monthly.xlsx")
LINK = re.compile(r'https://thedocs\.worldbank\.org/[^"\'\s<>]*CMO-Historical-Data-Monthly\.xlsx')

# Groups as the Pink Sheet organizes them, matched on the start of each series name.
GROUP_PREFIXES = [
    ("energy", ("Crude oil", "Coal", "Natural gas", "Liquefied natural gas")),
    ("beverages", ("Cocoa", "Coffee", "Tea")),
    ("oils_meals", ("Coconut oil", "Groundnut", "Fish meal", "Palm", "Soybean", "Rapeseed", "Sunflower")),
    ("grains", ("Barley", "Maize", "Sorghum", "Rice", "Wheat")),
    ("other_food", ("Banana", "Orange", "Beef", "Chicken", "Lamb", "Shrimp", "Sugar")),
    ("timber", ("Logs", "Sawnwood", "Plywood")),
    ("other_raw_materials", ("Tobacco", "Cotton", "Rubber")),
    ("fertilizers", ("Phosphate rock", "DAP", "TSP", "Urea", "Potassium chloride")),
    ("base_metals", ("Aluminum", "Iron ore", "Copper", "Lead", "Tin", "Nickel", "Zinc")),
    ("precious_metals", ("Gold", "Platinum", "Silver")),
]
# Commodities Indonesia is among the world's largest producers or exporters of (or, for coal, the Asian benchmark
# for the thermal coal it exports; for rubber, TSR20 is the grade Indonesia mainly exports).
INDONESIA = {"palm_oil", "palm_kernel_oil", "coconut_oil", "coal_australian", "nickel", "tin", "rubber_tsr20",
             "rubber_rss3", "coffee_robusta"}

INDEX_IDS = {  # Monthly Indices sheet, 2010 = 100
    "Total Index": "total", "Energy": "energy", "Non-energy": "non_energy", "Agriculture": "agriculture",
    "Beverages": "beverages", "Food": "food", "Oils & Meals": "oils_meals", "Grains": "grains",
    "Other Food": "other_food", "Raw Materials": "raw_materials", "Timber": "timber",
    "Other Raw Mat.": "other_raw_materials", "Fertilizers": "fertilizers", "Metals & Minerals": "metals_minerals",
    "Base Metals (ex. iron ore)": "base_metals", "Precious Metals": "precious_metals",
}
INDEX_NAMES = {
    "total": "all commodities", "energy": "energy", "non_energy": "all non-energy commodities",
    "agriculture": "agriculture", "beverages": "beverages", "food": "food", "oils_meals": "oils and meals",
    "grains": "grains", "other_food": "other food", "raw_materials": "agricultural raw materials",
    "timber": "timber", "other_raw_materials": "other raw materials (cotton, rubber, tobacco)",
    "fertilizers": "fertilizers", "metals_minerals": "metals and minerals",
    "base_metals": "base metals, excluding iron ore", "precious_metals": "precious metals",
}

PRICES = Table(
    name="prices_monthly",
    kind="history",  # the workbook holds the full history; each run rebuilds it (the World Bank revises months)
    description="Per commodity and month: average price in nominal US dollars, with month-on-month and year-on-year change. 71 commodities, since 1960.",
    key=("commodity_id", "month"),
    min_rows=40_000,
    columns=[
        Column("month", "datetime", "First day of the month"),
        Column("commodity_id", "string", "Short id, e.g. palm_oil, coal_australian, crude_oil_brent"),
        Column("commodity", "string", "Name as the World Bank gives it, e.g. 'Rice, Thai 5%'"),
        Column("group", "string", "Pink Sheet group: energy, beverages, oils_meals, grains, other_food, timber, other_raw_materials, fertilizers, base_metals, precious_metals"),
        Column("unit", "string", "Price unit, e.g. $/mt (US dollars per metric ton), $/bbl, $/kg, $/troy oz"),
        Column("price", "number", "Monthly average price in nominal US dollars per unit"),
        Column("mom_pct", "number", "Change from the previous month (%)"),
        Column("yoy_pct", "number", "Change from the same month a year before (%)"),
    ],
)

INDICES = Table(
    name="indices_monthly",
    kind="history",
    description="World Bank commodity price indices per month (nominal US dollars, 2010 = 100): total, energy, food, metals and 12 more.",
    key=("month",),
    min_rows=700,
    columns=[Column("month", "datetime", "First day of the month")]
    + [Column(i, "number", f"Price index for {n} (2010 = 100)") for i, n in INDEX_NAMES.items()],
)

COMMODITIES = Table(
    name="commodities",
    kind="derived",
    description="One row per commodity: unit, group, coverage, latest price, recent changes, all-time high and where today's price sits against its 10-year range.",
    key=("commodity_id",),
    min_rows=0,
    columns=[
        Column("commodity_id", "string", "Short id (joins prices_monthly)"),
        Column("commodity", "string", "World Bank name"),
        Column("group", "string", "Pink Sheet group"),
        Column("unit", "string", "Price unit"),
        Column("indonesia_major", "boolean", "Indonesia is among the largest producers or exporters (palm, coconut and palm kernel oil, coal, nickel, tin, rubber, robusta coffee)"),
        Column("first_month", "datetime", "First month with a price"),
        Column("last_month", "datetime", "Latest month with a price"),
        Column("months", "integer", "Months with a price"),
        Column("latest_price", "number", "Price in the latest month"),
        Column("change_1m_pct", "number", "Latest month vs the month before (%)"),
        Column("change_12m_pct", "number", "Latest month vs 12 months before (%)"),
        Column("change_5y_pct", "number", "Latest month vs 60 months before (%)"),
        Column("all_time_high", "number", "Highest monthly price on record (nominal)"),
        Column("all_time_high_month", "datetime", "Month of that high"),
        Column("avg_10y", "number", "Average price over the last 120 months"),
        Column("vs_10y_avg_pct", "number", "Latest price vs the 10-year average (%)"),
        Column("percentile_10y", "number", "Share of the last 120 months with a lower price (0-100): 100 = highest in 10 years"),
    ],
)

TABLES = [PRICES, INDICES, COMMODITIES]

# ---------- download and parsing ----------


def make_session():
    return base_session()


def workbook_url(session):
    """The current workbook link from the Commodity Markets page, or the last known one."""
    try:
        resp = session.get(PAGE, timeout=60)
        resp.raise_for_status()
        found = LINK.findall(resp.text)
        if found:
            return found[0]
        log.warning("No Pink Sheet link on %s; using the last known address", PAGE)
    except Exception as exc:  # noqa: BLE001 - the page is only a pointer; the fallback still works
        log.warning("Could not read %s (%s); using the last known address", PAGE, exc)
    return FALLBACK


def download(session):
    url = workbook_url(session)
    resp = session.get(url, timeout=300)
    resp.raise_for_status()
    log.info("Pink Sheet: %s (%d bytes)", url, len(resp.content))
    return resp.content


def clean_name(name):
    return re.sub(r"\s+", " ", str(name).replace("*", "")).strip()


def commodity_id(name):
    s = clean_name(name).lower().replace("%", "pct").replace("&", "and")
    s = s.replace("viet namese", "vietnamese").replace("u.v.", "uv")
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def group_of(name):
    for group, prefixes in GROUP_PREFIXES:
        if clean_name(name).startswith(prefixes):
            return group
    return "other"


def months(col):
    return pd.to_datetime(col.astype(str).str.strip(), format="%YM%m", errors="coerce")


def header_row(raw, label_col=0):
    """Index of the first row whose first cell is a month like 1960M01."""
    first = raw.iloc[:, label_col].astype(str).str.fullmatch(r"\d{4}M\d{2}")
    return int(first.idxmax()) if first.any() else None


def parse_prices(content):
    raw = pd.read_excel(io.BytesIO(content), sheet_name="Monthly Prices", header=None)
    start = header_row(raw)
    if start is None or start < 2:
        raise ValueError("Monthly Prices sheet: no month rows found")
    names, units = raw.iloc[start - 2, 1:], raw.iloc[start - 1, 1:]
    body = raw.iloc[start:]
    month = months(body.iloc[:, 0])
    frames = []
    for col, name, unit in zip(raw.columns[1:], names, units):
        if pd.isna(name) or not str(name).strip():
            continue
        price = pd.to_numeric(body[col], errors="coerce")  # ".." and "…" mark missing months
        frames.append(pd.DataFrame({
            "month": month, "commodity_id": commodity_id(name), "commodity": clean_name(name),
            "group": group_of(name), "unit": str(unit).strip().strip("()"), "price": price,
        }))
    df = pd.concat(frames, ignore_index=True).dropna(subset=["month", "price"])
    unknown = sorted(df.loc[df["group"] == "other", "commodity"].unique())
    if unknown:
        log.warning("Series in no known group (new in the Pink Sheet?): %s", unknown)
    return add_changes(df.sort_values(["commodity_id", "month"]).reset_index(drop=True))


def add_changes(df):
    """Month-on-month and year-on-year change, matched on calendar months (gaps stay empty, not misaligned)."""
    def shifted(months_back):
        prev = df[["commodity_id", "month", "price"]].assign(month=df["month"] + pd.DateOffset(months=months_back))
        merged = df[["commodity_id", "month"]].merge(prev, on=["commodity_id", "month"], how="left")
        return merged["price"].to_numpy()
    for col, back in (("mom_pct", 1), ("yoy_pct", 12)):
        before = pd.Series(shifted(back), index=df.index)
        df[col] = ((df["price"] / before - 1) * 100).round(2).where(before > 0)
    return df


def parse_indices(content):
    raw = pd.read_excel(io.BytesIO(content), sheet_name="Monthly Indices", header=None)
    start = header_row(raw)
    if start is None:
        raise ValueError("Monthly Indices sheet: no month rows found")
    out = pd.DataFrame({"month": months(raw.iloc[start:, 0])})
    for col in raw.columns[1:]:
        # The index name sits in one of the header rows above the data, indented by level.
        labels = [clean_name(v) for v in raw.iloc[max(0, start - 5):start, col] if pd.notna(v) and str(v).strip()]
        name = next((INDEX_IDS[n] for n in labels if n in INDEX_IDS), None)
        if name:
            out[name] = pd.to_numeric(raw.iloc[start:, col], errors="coerce").to_numpy()
    missing = [c for c in INDEX_NAMES if c not in out]
    if missing:
        raise ValueError(f"Monthly Indices sheet: indices not found: {missing}")
    return out.dropna(subset=["month"]).dropna(subset=list(INDEX_NAMES), how="all").reset_index(drop=True)


def make_fetchers(_, snapshot_date):
    session = make_session()
    cache = {}

    def content():
        if "x" not in cache:
            cache["x"] = download(session)
        return cache["x"]

    return {
        "prices_monthly": lambda previous: parse_prices(content()),
        "indices_monthly": lambda previous: parse_indices(content()),
    }


# ---------- derived ----------


def summarize(prices):
    if prices is None or prices.empty:
        return pd.DataFrame(columns=COMMODITIES.column_names)
    rows = []
    for cid, d in prices.sort_values("month").groupby("commodity_id", sort=True):
        s = d.set_index("month")["price"]
        last_month, latest = s.index[-1], s.iloc[-1]

        def change(months_back):
            before = s.get(last_month - pd.DateOffset(months=months_back))
            return round((latest / before - 1) * 100, 2) if before is not None and before > 0 else None

        recent = s[s.index > last_month - pd.DateOffset(months=120)]
        rows.append({
            "commodity_id": cid, "commodity": d["commodity"].iloc[-1], "group": d["group"].iloc[-1],
            "unit": d["unit"].iloc[-1], "indonesia_major": cid in INDONESIA,
            "first_month": s.index[0], "last_month": last_month, "months": len(s), "latest_price": latest,
            "change_1m_pct": change(1), "change_12m_pct": change(12), "change_5y_pct": change(60),
            "all_time_high": s.max(), "all_time_high_month": s.idxmax(),
            "avg_10y": round(recent.mean(), 4),
            "vs_10y_avg_pct": round((latest / recent.mean() - 1) * 100, 2) if recent.mean() > 0 else None,
            "percentile_10y": round(100 * (recent < latest).mean(), 1),
        })
    return pd.DataFrame(rows)[COMMODITIES.column_names]


def derive(frames):
    return {"commodities": summarize(frames.get("prices_monthly"))}


# ---------- description ----------


def movers_markdown(frames):
    summary = summarize((frames or {}).get("prices_monthly"))
    if summary.empty:
        return "(computed when the dataset is built)"
    latest = summary["last_month"].max()
    cur = summary[(summary["last_month"] == latest) & ~summary["unit"].str.contains("=100")].dropna(subset=["change_12m_pct"])
    lines = [f"Latest month: **{latest:%B %Y}**. Biggest changes over 12 months:", "",
             "| Commodity | Price | 12-month change |", "|---|---|---|"]
    top = pd.concat([cur.nlargest(4, "change_12m_pct"), cur.nsmallest(4, "change_12m_pct")])
    for _, r in top.iterrows():
        lines.append(f"| {r['commodity']} | {r['latest_price']:,.2f} {r['unit']} | {r['change_12m_pct']:+.1f}% |")
    idn = summary[summary["indonesia_major"]].sort_values("commodity")
    if not idn.empty:
        lines += ["", "Indonesia's key commodities:", "", "| Commodity | Price | 12-month change | vs 10-year average |",
                  "|---|---|---|---|"]
        for _, r in idn.iterrows():
            ch = f"{r['change_12m_pct']:+.1f}%" if pd.notna(r["change_12m_pct"]) else "–"
            vs = f"{r['vs_10y_avg_pct']:+.1f}%" if pd.notna(r["vs_10y_avg_pct"]) else "–"
            lines.append(f"| {r['commodity']} | {r['latest_price']:,.2f} {r['unit']} | {ch} | {vs} |")
    return "\n".join(lines)


def describe(snapshot_date, tables_written, frames=None):
    return "\n".join([
        "**Monthly world prices for 71 commodities since 1960**, from the World Bank's \"Pink Sheet\": crude oil, "
        "coal, natural gas, palm oil, rice, wheat, sugar, coffee, cocoa, rubber, fertilizers, nickel, tin, copper, "
        "iron ore, gold and more, plus 16 price indices. Rebuilt every month from the official workbook, in tidy "
        "tables ready for analysis.",
        "",
        "## Why this dataset",
        "",
        "- **Long and consistent**: 65+ years of monthly prices in one place, through the 1970s oil shocks, the "
        "2008 food crisis, the 2022 energy spike and everything since.",
        "- **Tidy, not a spreadsheet**: one row per commodity and month with units, groups and month-on-month and "
        "year-on-year change already computed; a summary table says where each price sits against its 10-year "
        "range.",
        "- **Indonesia lens**: the commodities Indonesia is among the largest producers or exporters of (palm oil, "
        "coal, nickel, tin, rubber, robusta coffee, coconut oil) are flagged, for work on export earnings, the "
        "rupiah or inflation.",
        "",
        "## Files",
        "",
        files_markdown(tables_written),
        "",
        "## Latest movements",
        "",
        movers_markdown(frames),
        "",
        "## How to read it",
        "",
        "- **Nominal US dollars**: prices are not adjusted for inflation. To compare across decades, deflate them "
        "(for example by the US CPI) or compare against the indices.",
        "- **Monthly averages** of the benchmark the World Bank tracks for each commodity (e.g. coal: Newcastle "
        "f.o.b.; nickel and tin: London Metal Exchange; rubber: Singapore exchange). Some benchmarks were "
        "replaced over the years (palm oil most recently in January 2026), so a change across such a switch "
        "mixes market movement with the new specification; the World Bank's workbook documents each one.",
        "- **`natural_gas_index`** is the only series in `prices_monthly` that is an index (2010 = 100), not a "
        "price, as in the World Bank's own sheet.",
        "- **Gaps** are months the World Bank has no quote for; changes are computed only between real months, "
        "never across a gap.",
        "- **Revisions**: the most recent months are sometimes revised in the next release.",
        "",
        "## Updates",
        "",
        f"Rebuilt monthly, a few days after the World Bank's release early each month. Last update: "
        f"{snapshot_date:%Y-%m-%d} (UTC).",
        "",
        "## Source and terms",
        "",
        "World Bank Commodity Price Data (The Pink Sheet), https://www.worldbank.org/en/research/commodity-markets, "
        "licensed CC BY 4.0. Cite the World Bank when you use it. This dataset only reorganizes the published data "
        "and is not affiliated with the World Bank.",
    ])


SPEC = DatasetSpec(
    name="commodities",
    slug="world-commodity-prices-monthly-pink-sheet",
    title="World Commodity Prices Monthly (1960-now)",
    subtitle="71 commodities from oil, coal and palm oil to nickel and gold, World Bank data",
    license="CC-BY-4.0",
    keywords=["economics", "finance", "investing", "time series analysis", "tabular"],
    tables=TABLES,
    sources=("World Bank Commodity Price Data (The Pink Sheet), https://www.worldbank.org/en/research/commodity-markets, "
             "CC BY 4.0. Built monthly by https://github.com/daniel766hi/kaggle-compe"),
    make_fetchers=make_fetchers,
    derive=derive,
    describe=describe,
    cover=ASSETS / "commodities-cover.png",
    update_frequency="monthly",
    run_days=(5, 12),  # the Pink Sheet comes out on the 2nd-3rd business day; the 12th catches a late release
)
