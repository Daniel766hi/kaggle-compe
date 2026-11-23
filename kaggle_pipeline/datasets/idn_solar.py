"""Indonesia solar resource: daily sunlight, temperature, rain and wind for all 38 provincial capitals (NASA POWER).

Source: NASA Prediction Of Worldwide Energy Resources (POWER), https://power.larc.nasa.gov, Renewable Energy
community, daily point data. Values are satellite- and model-derived estimates for the 0.5 x 0.625 degree grid cell
around each city (not ground measurements). NASA POWER data are free to use; NASA asks users to acknowledge the
POWER project. The most recent days can be missing (-999 in the source) until NASA processes them.
"""

import logging
import time
from pathlib import Path

import pandas as pd

from ..http import make_session as base_session
from ..schema import Column, DatasetSpec, Table, files_markdown

log = logging.getLogger(__name__)

ASSETS = Path(__file__).resolve().parents[2] / "assets"
API = "https://power.larc.nasa.gov/api/temporal/daily/point"
START = "20010101"
PERFORMANCE_RATIO = 0.80  # typical rooftop PV system losses (inverter, heat, dust, wiring); an assumption, stated

PARAMS = {  # NASA POWER parameter -> column
    "ALLSKY_SFC_SW_DWN": "ghi_kwh_m2", "CLRSKY_SFC_SW_DWN": "clear_sky_ghi_kwh_m2", "ALLSKY_KT": "clearness_index",
    "T2M": "temp_c", "T2M_MAX": "temp_max_c", "T2M_MIN": "temp_min_c", "RH2M": "humidity_pct",
    "PRECTOTCORR": "rain_mm", "WS10M": "wind_ms",
}

# Provincial capitals (38 provinces, 2026). Coordinates of the city centre.
CITIES = [
    ("Banda Aceh", "Aceh", 5.5483, 95.3238), ("Medan", "Sumatera Utara", 3.5952, 98.6722),
    ("Padang", "Sumatera Barat", -0.9471, 100.4172), ("Pekanbaru", "Riau", 0.5071, 101.4478),
    ("Tanjung Pinang", "Kepulauan Riau", 0.9186, 104.4554), ("Jambi", "Jambi", -1.6101, 103.6131),
    ("Palembang", "Sumatera Selatan", -2.9761, 104.7754), ("Pangkal Pinang", "Kepulauan Bangka Belitung", -2.1316, 106.1169),
    ("Bengkulu", "Bengkulu", -3.7928, 102.2608), ("Bandar Lampung", "Lampung", -5.3971, 105.2668),
    ("Jakarta", "DKI Jakarta", -6.2088, 106.8456), ("Serang", "Banten", -6.1200, 106.1503),
    ("Bandung", "Jawa Barat", -6.9175, 107.6191), ("Semarang", "Jawa Tengah", -6.9667, 110.4167),
    ("Yogyakarta", "DI Yogyakarta", -7.7956, 110.3695), ("Surabaya", "Jawa Timur", -7.2575, 112.7521),
    ("Denpasar", "Bali", -8.6500, 115.2167), ("Mataram", "Nusa Tenggara Barat", -8.5833, 116.1167),
    ("Kupang", "Nusa Tenggara Timur", -10.1772, 123.6070), ("Pontianak", "Kalimantan Barat", -0.0263, 109.3425),
    ("Palangka Raya", "Kalimantan Tengah", -2.2161, 113.9135), ("Banjarbaru", "Kalimantan Selatan", -3.4425, 114.8389),
    ("Samarinda", "Kalimantan Timur", -0.5022, 117.1536), ("Tanjung Selor", "Kalimantan Utara", 2.8375, 117.3653),
    ("Manado", "Sulawesi Utara", 1.4748, 124.8421), ("Gorontalo", "Gorontalo", 0.5435, 123.0568),
    ("Palu", "Sulawesi Tengah", -0.8917, 119.8707), ("Mamuju", "Sulawesi Barat", -2.6748, 118.8885),
    ("Makassar", "Sulawesi Selatan", -5.1477, 119.4327), ("Kendari", "Sulawesi Tenggara", -3.9985, 122.5129),
    ("Ambon", "Maluku", -3.6954, 128.1814), ("Sofifi", "Maluku Utara", 0.7372, 127.5587),
    ("Jayapura", "Papua", -2.5337, 140.7181), ("Manokwari", "Papua Barat", -0.8615, 134.0620),
    ("Sorong", "Papua Barat Daya", -0.8762, 131.2558), ("Merauke", "Papua Selatan", -8.4932, 140.4018),
    ("Nabire", "Papua Tengah", -3.3616, 135.4960), ("Wamena", "Papua Pegunungan", -4.0973, 138.9425),
]

DAILY = Table(
    name="solar_daily",
    kind="history",  # each run refetches the full series, so NASA's corrections to recent days come through
    description="Per city and day since 2001: sunlight on a flat surface (kWh/m2), clear-sky sunlight, temperature, humidity, rain and wind.",
    key=("city", "date"),
    min_rows=300_000,
    max_shrink=0.01,
    columns=[
        Column("date", "datetime", "Day"),
        Column("city", "string", "Provincial capital"),
        Column("province", "string", "Province"),
        Column("ghi_kwh_m2", "number", "All-sky global horizontal irradiance: solar energy on a flat surface (kWh/m2/day)"),
        Column("clear_sky_ghi_kwh_m2", "number", "Same under a cloudless sky (kWh/m2/day); the gap to ghi is what clouds take"),
        Column("clearness_index", "number", "Share of top-of-atmosphere sunlight reaching the ground (0-1)"),
        Column("temp_c", "number", "Mean air temperature at 2 m (degrees C)"),
        Column("temp_max_c", "number", "Maximum air temperature at 2 m (degrees C)"),
        Column("temp_min_c", "number", "Minimum air temperature at 2 m (degrees C)"),
        Column("humidity_pct", "number", "Relative humidity at 2 m (%)"),
        Column("rain_mm", "number", "Precipitation, bias-corrected (mm/day)"),
        Column("wind_ms", "number", "Mean wind speed at 10 m (m/s)"),
    ],
)

CITIES_T = Table(
    name="cities",
    kind="derived",
    description="One row per provincial capital: location and long-term solar resource, with an estimated rooftop PV yield.",
    key=("city",),
    min_rows=0,
    columns=[
        Column("city", "string", "Provincial capital"),
        Column("province", "string", "Province"),
        Column("latitude", "number", "Latitude of the city centre"),
        Column("longitude", "number", "Longitude of the city centre"),
        Column("years", "number", "Years of complete data used for the averages"),
        Column("ghi_kwh_m2_day", "number", "Average daily solar energy on a flat surface (kWh/m2/day)"),
        Column("ghi_kwh_m2_year", "number", "Average yearly solar energy on a flat surface (kWh/m2/year)"),
        Column("pv_kwh_per_kwp_year", "number", "Estimated yearly output of 1 kWp of flat rooftop PV, at an 80% performance ratio"),
        Column("best_month", "integer", "Calendar month with the most sun (1-12)"),
        Column("worst_month", "integer", "Calendar month with the least sun (1-12)"),
        Column("seasonal_swing_pct", "number", "Sunniest month vs least sunny month, as % above the least sunny"),
        Column("rain_mm_year", "number", "Average yearly rainfall (mm)"),
        Column("rank_ghi", "integer", "Rank among the 38 capitals by solar energy (1 = sunniest)"),
    ],
)

MONTHLY = Table(
    name="solar_monthly",
    kind="derived",
    description="Per city and month: total sunlight, estimated rooftop PV output per kWp, mean temperature and total rain.",
    key=("city", "month"),
    min_rows=0,
    columns=[
        Column("month", "datetime", "First day of the month"),
        Column("city", "string", "Provincial capital"),
        Column("days", "integer", "Days with data in the month"),
        Column("ghi_kwh_m2", "number", "Total solar energy on a flat surface in the month (kWh/m2)"),
        Column("pv_kwh_per_kwp", "number", "Estimated output of 1 kWp of flat rooftop PV (kWh), at an 80% performance ratio"),
        Column("temp_c", "number", "Mean temperature (degrees C)"),
        Column("rain_mm", "number", "Total rain (mm)"),
    ],
)

TABLES = [DAILY, CITIES_T, MONTHLY]

# ---------- download ----------


def make_session():
    return base_session()


def fetch_city(session, lat, lon, end):
    params = {"parameters": ",".join(PARAMS), "community": "RE", "latitude": lat, "longitude": lon,
              "start": START, "end": end, "format": "JSON", "time-standard": "LST"}
    for attempt in range(3):
        resp = session.get(API, params=params, timeout=300)
        if resp.status_code in (429, 500, 502, 503) and attempt < 2:
            time.sleep(30)
            continue
        resp.raise_for_status()
        break
    data = resp.json()
    fill = data.get("header", {}).get("fill_value", -999.0)
    values = data["properties"]["parameter"]
    df = pd.DataFrame({PARAMS[p]: pd.Series(values[p]) for p in PARAMS})
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    return df.mask(df == fill).rename_axis("date").reset_index()


def fetch_all(session, snapshot_date, pause_s=1.0):
    end = (snapshot_date - pd.Timedelta(days=1)).strftime("%Y%m%d")
    frames = []
    for city, province, lat, lon in CITIES:
        df = fetch_city(session, lat, lon, end).assign(city=city, province=province)
        frames.append(df)
        log.info("NASA POWER %s: %d days", city, len(df))
        time.sleep(pause_s)
    df = pd.concat(frames, ignore_index=True)
    # Drop trailing days NASA has not processed yet (all values missing), keep gaps inside the series as they are.
    df = df.dropna(subset=list(PARAMS.values()), how="all")
    return df[DAILY.column_names].sort_values(["city", "date"]).reset_index(drop=True)


def make_fetchers(_, snapshot_date):
    session = make_session()
    return {"solar_daily": lambda previous: fetch_all(session, snapshot_date)}


# ---------- derived ----------


def monthly(daily):
    if daily is None or daily.empty:
        return pd.DataFrame(columns=MONTHLY.column_names)
    d = daily.assign(month=daily["date"].dt.to_period("M").dt.to_timestamp())
    last = d["date"].max()
    d = d[d["month"] + pd.offsets.MonthEnd(0) <= last]  # complete months only
    g = d.groupby(["city", "month"])
    out = pd.DataFrame({"days": g["ghi_kwh_m2"].count(), "ghi_kwh_m2": g["ghi_kwh_m2"].sum(min_count=1),
                        "temp_c": g["temp_c"].mean(), "rain_mm": g["rain_mm"].sum(min_count=1)}).reset_index()
    out["pv_kwh_per_kwp"] = out["ghi_kwh_m2"] * PERFORMANCE_RATIO  # 1 kWp produces ~1 kWh per kWh/m2 at standard conditions
    out[["ghi_kwh_m2", "pv_kwh_per_kwp", "temp_c", "rain_mm"]] = out[["ghi_kwh_m2", "pv_kwh_per_kwp", "temp_c", "rain_mm"]].round(2)
    return out[MONTHLY.column_names]


def cities(daily):
    if daily is None or daily.empty:
        return pd.DataFrame(columns=CITIES_T.column_names)
    coords = {c: (lat, lon) for c, _, lat, lon in CITIES}
    full_years = daily.assign(year=daily["date"].dt.year)
    counts = full_years.groupby(["city", "year"])["ghi_kwh_m2"].count()
    rows = []
    for (city, province), d in daily.groupby(["city", "province"]):
        years = [y for y in counts.loc[city].index if counts.loc[(city, y)] >= 360]  # complete years only
        d = d[d["date"].dt.year.isin(years)]
        by_month = d.groupby(d["date"].dt.month)["ghi_kwh_m2"].mean()
        ghi_day = d["ghi_kwh_m2"].mean()
        rows.append({
            "city": city, "province": province, "latitude": coords[city][0], "longitude": coords[city][1],
            "years": len(years), "ghi_kwh_m2_day": round(ghi_day, 3), "ghi_kwh_m2_year": round(ghi_day * 365.25, 1),
            "pv_kwh_per_kwp_year": round(ghi_day * 365.25 * PERFORMANCE_RATIO, 1),
            "best_month": int(by_month.idxmax()), "worst_month": int(by_month.idxmin()),
            "seasonal_swing_pct": round((by_month.max() / by_month.min() - 1) * 100, 1),
            "rain_mm_year": round(d["rain_mm"].mean() * 365.25, 0),
        })
    out = pd.DataFrame(rows)
    out["rank_ghi"] = out["ghi_kwh_m2_day"].rank(ascending=False, method="min").astype(int)
    return out.sort_values("rank_ghi")[CITIES_T.column_names].reset_index(drop=True)


def derive(frames):
    daily = frames.get("solar_daily")
    return {"cities": cities(daily), "solar_monthly": monthly(daily)}


# ---------- description ----------


def overview(frames):
    c = cities((frames or {}).get("solar_daily"))
    if c.empty:
        return "(computed when the dataset is built)"
    daily = frames["solar_daily"]
    top, bottom = c.head(5), c.tail(5)
    line = lambda r: f"| {r.city} | {r.province} | {r.ghi_kwh_m2_day:.2f} | {r.pv_kwh_per_kwp_year:,.0f} | {r.seasonal_swing_pct:.0f}% |"
    return "\n".join([
        f"Daily data from {daily['date'].min():%d %b %Y} to {daily['date'].max():%d %b %Y} for 38 provincial capitals.", "",
        "| City | Province | Sun (kWh/m2/day) | PV yield (kWh/kWp/year, est.) | Seasonal swing |", "|---|---|---|---|---|",
        *[line(r) for r in top.itertuples()], "| ... | | | | |", *[line(r) for r in bottom.itertuples()],
    ])


def describe(snapshot_date, tables_written, frames=None):
    return "\n".join([
        "**How much solar energy every Indonesian province gets, day by day since 2001**: sunlight on a flat surface, "
        "clear-sky sunlight, cloudiness, temperature, humidity, rain and wind for all 38 provincial capitals, from "
        "NASA's POWER project, plus monthly totals and an estimated rooftop solar output per city.",
        "",
        "## Why this dataset",
        "",
        "- **Solar planning**: compare cities and seasons before sizing a rooftop PV system, a solar roof tile or a "
        "solar-powered cold chain.",
        "- **Energy and climate analysis**: link sunlight to rain seasons, temperature trends and Indonesia's "
        "renewable energy targets.",
        "- **Clean and complete**: one tidy table, missing values left empty instead of NASA's -999 code, and "
        "derived monthly and per-city tables.",
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
        "- **Estimates for a grid cell**: NASA POWER derives these values from satellites and weather models for "
        "a cell of about 55 x 70 km around each city; they are not readings from a weather station.",
        "- **ghi_kwh_m2** is the energy that falls on a flat, unshaded surface per day. A tilted panel facing the "
        "equator collects somewhat more.",
        "- **PV yield** multiplies sunlight by an 80% performance ratio, a common rule of thumb for system losses; "
        "real systems vary with tilt, shading, dust, heat and equipment.",
        "- **Recent days** can be missing until NASA processes them; they fill in on later updates.",
        "",
        "## Updates",
        "",
        f"Rebuilt monthly. Last update: {snapshot_date:%Y-%m-%d} (UTC).",
        "",
        "## Source and terms",
        "",
        "Data obtained from the NASA Langley Research Center (LaRC) POWER Project funded through the NASA Earth "
        "Science/Applied Science Program (https://power.larc.nasa.gov). NASA POWER data are freely available; please "
        "acknowledge the POWER project when you use them. Not affiliated with NASA.",
    ])


SPEC = DatasetSpec(
    name="idn-solar",
    slug="indonesia-solar-irradiance-38-provinces-nasa",
    title="Indonesia Solar Irradiance: 38 Provinces Daily",
    subtitle="Daily sunlight, temperature and rain since 2001 for every provincial capital",
    license="other",
    keywords=["asia", "environment", "weather and climate", "time series analysis", "tabular"],
    tables=TABLES,
    sources="NASA Langley Research Center POWER Project (https://power.larc.nasa.gov), daily point data, Renewable "
            "Energy community. Built monthly by https://github.com/daniel766hi/kaggle-compe",
    make_fetchers=make_fetchers,
    derive=derive,
    describe=describe,
    cover=ASSETS / "idn-solar-cover.png",
    update_frequency="monthly",
    run_days=(4,),
)
