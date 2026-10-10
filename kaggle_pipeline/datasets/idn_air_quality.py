"""Indonesia air quality: hourly PM2.5, PM10 and gases for 31 cities, from Open-Meteo (CAMS)."""

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from ..schema import Column, DatasetSpec, Table, files_markdown
from . import open_meteo as om

ASSETS = Path(__file__).resolve().parents[2] / "assets"
URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
FIRST_DAY = date(2022, 8, 1)  # global CAMS history on Open-Meteo starts mid-2022
RECENT_DAYS = 7
CHUNK_DAYS = 92
WHO_PM25_24H = 15  # WHO 2021 air quality guideline, 24-hour mean, µg/m³

HOURLY = {
    "pm2_5": "Particulate matter < 2.5 µm (µg/m³)",
    "pm10": "Particulate matter < 10 µm (µg/m³)",
    "carbon_monoxide": "Carbon monoxide (µg/m³)",
    "nitrogen_dioxide": "Nitrogen dioxide (µg/m³)",
    "sulphur_dioxide": "Sulphur dioxide (µg/m³)",
    "ozone": "Ozone (µg/m³)",
    "dust": "Mineral dust (µg/m³)",
    "uv_index": "UV index",
    "us_aqi": "US EPA Air Quality Index (0-500, max over pollutants)",
}

CITY_COLUMNS = [
    Column("city", "string", "City name"),
    Column("province", "string", "Province"),
    Column("island", "string", "Island group"),
]

TABLES = [
    Table(
        name="idn_air_quality_hourly",
        kind="incremental",
        fmt="parquet",
        description="Hourly air quality for 31 Indonesian cities. One row per city per hour.",
        columns=CITY_COLUMNS + [
            Column("time_local", "datetime", "Local time at the city (WIB, WITA or WIT)"),
            Column("time_utc", "datetime", "Time in UTC"),
        ] + [Column(name, "number", desc) for name, desc in HOURLY.items()],
        min_rows=1000,
        key=("city", "time_utc"),
    ),
    Table(
        name="idn_air_quality_daily",
        kind="derived",
        description="Daily air quality summary per city, with the WHO PM2.5 guideline check.",
        columns=CITY_COLUMNS + [
            Column("date", "datetime", "Local date"),
            Column("pm2_5_mean", "number", "Daily mean PM2.5 (µg/m³)"),
            Column("pm2_5_max", "number", "Highest hourly PM2.5 that day (µg/m³)"),
            Column("pm10_mean", "number", "Daily mean PM10 (µg/m³)"),
            Column("us_aqi_mean", "number", "Daily mean US AQI"),
            Column("us_aqi_max", "number", "Highest hourly US AQI that day"),
            Column("hours", "integer", "Hours with a PM2.5 value (24 = complete day)"),
            Column("exceeds_who_pm25", "boolean", f"Daily mean PM2.5 above the WHO 24-hour guideline ({WHO_PM25_24H} µg/m³)"),
        ],
        key=("city", "date"),
    ),
    Table(
        name="cities",
        kind="derived",
        description="The 31 cities covered, with province, island group and the coordinates used.",
        columns=CITY_COLUMNS + [
            Column("latitude", "number", "Latitude used for the data request"),
            Column("longitude", "number", "Longitude used for the data request"),
        ],
        key=("city",),
    ),
]


def parse(raw, city):
    hourly = (raw or {}).get("hourly") or {}
    if not hourly.get("time"):
        return None
    offset = pd.Timedelta(seconds=(raw or {}).get("utc_offset_seconds") or 0)
    local = pd.to_datetime(pd.Series(hourly["time"]))
    df = pd.DataFrame({"time_local": local, "time_utc": local - offset})
    for name in HOURLY:
        df[name] = hourly.get(name)
    return om.with_city_columns(df, city)


def make_fetchers(_, snapshot_date):
    session = om.session()
    last_day = snapshot_date.date() - timedelta(days=1)  # full days only

    def fetch(previous):
        coverage = om.coverage_of(previous, "time_local")
        jobs = om.plan(coverage, list(om.CITY_INFO), FIRST_DAY, last_day, RECENT_DAYS, CHUNK_DAYS)

        def one(job):
            info = om.CITY_INFO[job.city]
            raw = om.request(session, URL, {
                "latitude": info["latitude"], "longitude": info["longitude"],
                "hourly": ",".join(HOURLY), "timezone": "auto",
                "start_date": job.start.isoformat(), "end_date": job.end.isoformat(),
            })
            return parse(raw, job.city)

        return om.run_jobs(jobs, one, n_vars=len(HOURLY))

    return {"idn_air_quality_hourly": fetch}


def daily(hourly):
    df = hourly.assign(date=hourly["time_local"].dt.normalize())
    g = df.groupby(["city", "province", "island", "date"])
    out = g.agg(
        pm2_5_mean=("pm2_5", "mean"), pm2_5_max=("pm2_5", "max"), pm10_mean=("pm10", "mean"),
        us_aqi_mean=("us_aqi", "mean"), us_aqi_max=("us_aqi", "max"), hours=("pm2_5", "count"),
    ).reset_index()
    out["exceeds_who_pm25"] = (out["pm2_5_mean"] > WHO_PM25_24H).where(out["pm2_5_mean"].notna())
    out["exceeds_who_pm25"] = out["exceeds_who_pm25"].map(lambda v: bool(v) if pd.notna(v) else pd.NA)
    return out


def derive(frames):
    return {"idn_air_quality_daily": daily(frames["idn_air_quality_hourly"]), "cities": om.cities_frame()}


def describe(snapshot_date, tables_written):
    return "\n".join([
        "Hourly **air quality for 31 Indonesian cities**, from Banda Aceh to Jayapura: PM2.5, PM10, "
        "carbon monoxide, nitrogen dioxide, sulphur dioxide, ozone, dust, UV index and the US AQI.",
        "",
        "## Why this dataset",
        "",
        "Jakarta regularly ranks among the most polluted cities in the world, but consistent, "
        "nationwide air quality data is hard to find. This dataset gives one clean time series per "
        "city, updated every day, with a daily summary that flags days above the WHO PM2.5 guideline. "
        "Use it for pollution trends, city comparisons, seasonal patterns (dry season, haze from "
        "forest fires), or forecasting.",
        "",
        "## Files",
        "",
        files_markdown(tables_written),
        "",
        "## Updates",
        "",
        f"Refreshed daily by an automated pipeline. Last update: {snapshot_date:%Y-%m-%d} (UTC). "
        f"Each run re-fetches the last {RECENT_DAYS} days. History goes back to "
        f"{FIRST_DAY:%B %Y} and was loaded gradually over the first runs to respect the API's free limits.",
        "",
        "## Source and attribution",
        "",
        "Data from [Open-Meteo](https://open-meteo.com) Air Quality API, licensed "
        "[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Generated using Copernicus "
        "Atmosphere Monitoring Service (CAMS) information. Please credit Open-Meteo and CAMS.",
        "",
        "## Important: these are model estimates",
        "",
        "Values come from the CAMS global atmospheric model (about 40 km grid), not from ground "
        "monitoring stations. They capture regional pollution and trends well, but can differ "
        "from a local station reading, especially for street-level spikes. Use them for comparisons "
        "and trends rather than as official measurements.",
        "",
        "## Notes",
        "",
        "- `time_local` uses each city's own time zone (WIB, WITA or WIT); `time_utc` is the same moment in UTC.",
        f"- `exceeds_who_pm25` compares the daily mean with the WHO 2021 24-hour guideline of {WHO_PM25_24H} µg/m³.",
        "- Empty values mean the source had no data for that hour.",
    ])


SPEC = DatasetSpec(
    name="idn-air-quality",
    slug="indonesia-air-quality-hourly-pm25",
    title="Indonesia Air Quality: Hourly PM2.5, 31 Cities",
    subtitle="Hourly PM2.5, PM10, gases and AQI for 31 Indonesian cities, updated daily",
    license="CC-BY-4.0",
    keywords=["environment", "pollution", "time series analysis", "indonesia"],
    tables=TABLES,
    sources=(
        "Open-Meteo Air Quality API (https://open-meteo.com/en/docs/air-quality-api), CC BY 4.0; "
        "underlying data: Copernicus Atmosphere Monitoring Service (CAMS) global forecasts and analyses. "
        "Collected daily by https://github.com/daniel766hi/kaggle-compe"
    ),
    make_fetchers=make_fetchers,
    describe=describe,
    derive=derive,
    cover=ASSETS / "idn-air-quality-cover.png",
)
