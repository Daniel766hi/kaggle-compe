"""Indonesia daily weather for 31 cities since 2000, from the Open-Meteo historical weather API."""

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from ..schema import Column, DatasetSpec, Table, files_markdown
from . import open_meteo as om

ASSETS = Path(__file__).resolve().parents[2] / "assets"
URL = "https://archive-api.open-meteo.com/v1/archive"
FIRST_DAY = date(2000, 1, 1)
RECENT_DAYS = 14  # the archive lags a few days and recent values get revised
CHUNK_DAYS = 366
RAINY_DAY_MM = 1.0

DAILY = {
    "weather_code": "WMO weather code (most severe condition of the day)",
    "temperature_2m_max": "Maximum air temperature at 2 m (°C)",
    "temperature_2m_min": "Minimum air temperature at 2 m (°C)",
    "temperature_2m_mean": "Mean air temperature at 2 m (°C)",
    "precipitation_sum": "Total precipitation (mm)",
    "precipitation_hours": "Hours with precipitation (h)",
    "wind_speed_10m_max": "Maximum wind speed at 10 m (km/h)",
    "wind_gusts_10m_max": "Maximum wind gust at 10 m (km/h)",
    "shortwave_radiation_sum": "Total solar radiation (MJ/m²)",
    "et0_fao_evapotranspiration": "Reference evapotranspiration, FAO-56 (mm)",
}

CITY_COLUMNS = [
    Column("city", "string", "City name"),
    Column("province", "string", "Province"),
    Column("island", "string", "Island group"),
]

TABLES = [
    Table(
        name="idn_weather_daily",
        kind="incremental",
        description="Daily weather for 31 Indonesian cities since 2000. One row per city per day.",
        columns=CITY_COLUMNS + [Column("date", "datetime", "Local date")]
        + [Column(name, "number", desc) for name, desc in DAILY.items()],
        min_rows=100,
        key=("city", "date"),
    ),
    Table(
        name="idn_weather_monthly",
        kind="derived",
        description="Monthly climate summary per city: temperatures, total rainfall and rainy days.",
        columns=CITY_COLUMNS + [
            Column("month", "datetime", "First day of the month"),
            Column("temperature_mean", "number", "Average daily mean temperature (°C)"),
            Column("temperature_max_mean", "number", "Average daily maximum temperature (°C)"),
            Column("temperature_min_mean", "number", "Average daily minimum temperature (°C)"),
            Column("precipitation_total", "number", "Total precipitation in the month (mm)"),
            Column("rainy_days", "integer", f"Days with at least {RAINY_DAY_MM:g} mm of precipitation"),
            Column("days", "integer", "Days with data in the month"),
        ],
        key=("city", "month"),
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
    daily = (raw or {}).get("daily") or {}
    if not daily.get("time"):
        return None
    df = pd.DataFrame({"date": pd.to_datetime(pd.Series(daily["time"]))})
    for name in DAILY:
        df[name] = daily.get(name)
    return om.with_city_columns(df, city)


def make_fetchers(_, snapshot_date):
    session = om.session()
    last_day = snapshot_date.date() - timedelta(days=1)

    def fetch(previous):
        coverage = om.coverage_of(previous, "date")
        jobs = om.plan(coverage, list(om.CITY_INFO), FIRST_DAY, last_day, RECENT_DAYS, CHUNK_DAYS)

        def one(job):
            info = om.CITY_INFO[job.city]
            raw = om.request(session, URL, {
                "latitude": info["latitude"], "longitude": info["longitude"],
                "daily": ",".join(DAILY), "timezone": "auto",
                "start_date": job.start.isoformat(), "end_date": job.end.isoformat(),
            })
            return parse(raw, job.city)

        return om.run_jobs(jobs, one, n_vars=len(DAILY))

    return {"idn_weather_daily": fetch}


def monthly(daily):
    df = daily.assign(month=daily["date"].dt.to_period("M").dt.to_timestamp())
    df["rainy"] = (df["precipitation_sum"] >= RAINY_DAY_MM).where(df["precipitation_sum"].notna())
    g = df.groupby(["city", "province", "island", "month"])
    return g.agg(
        temperature_mean=("temperature_2m_mean", "mean"),
        temperature_max_mean=("temperature_2m_max", "mean"),
        temperature_min_mean=("temperature_2m_min", "mean"),
        precipitation_total=("precipitation_sum", lambda s: s.sum(min_count=1)),
        rainy_days=("rainy", "sum"),
        days=("temperature_2m_mean", "count"),
    ).reset_index()


def derive(frames):
    return {"idn_weather_monthly": monthly(frames["idn_weather_daily"]), "cities": om.cities_frame()}


def describe(snapshot_date, tables_written):
    return "\n".join([
        "Daily **weather for 31 Indonesian cities since 2000**, from Banda Aceh to Jayapura: "
        "temperature, rainfall, wind, solar radiation and evapotranspiration.",
        "",
        "## Why this dataset",
        "",
        "One consistent daily series for every major Indonesian city, updated every day. Use it to "
        "study the wet and dry seasons, El Niño and La Niña years, rainfall trends, heat, or as "
        "weather features for demand, agriculture, logistics and energy models.",
        "",
        "## Files",
        "",
        files_markdown(tables_written),
        "",
        "## Updates",
        "",
        f"Refreshed daily by an automated pipeline. Last update: {snapshot_date:%Y-%m-%d} (UTC). "
        f"The newest days arrive with a delay of a few days, and each run re-fetches the last "
        f"{RECENT_DAYS} days because recent values get revised. History back to {FIRST_DAY.year} "
        "was loaded gradually over the first runs to respect the API's free limits.",
        "",
        "## Source and attribution",
        "",
        "Data from the [Open-Meteo](https://open-meteo.com) Historical Weather API, licensed "
        "[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Contains modified Copernicus "
        "Climate Change Service information (ERA5 reanalysis). Please credit Open-Meteo and ECMWF/Copernicus.",
        "",
        "## Important: these are model (reanalysis) values",
        "",
        "Values come from weather reanalysis models (grid of about 9-25 km), not from a single "
        "weather station. They are consistent across cities and years, which makes them good for "
        "comparisons and trends, but local rain showers in particular can differ from a station record.",
        "",
        "## Notes",
        "",
        "- Dates are local dates in each city's own time zone (WIB, WITA or WIT).",
        f"- A rainy day in the monthly file means at least {RAINY_DAY_MM:g} mm of precipitation.",
        "- `weather_code` follows the WMO code table (0 = clear sky, 61-65 = rain, 95 = thunderstorm, ...).",
    ])


SPEC = DatasetSpec(
    name="idn-weather",
    slug="indonesia-daily-weather-31-cities",
    title="Indonesia Daily Weather: 31 Cities since 2000",
    subtitle="Daily temperature, rain, wind and sun for 31 Indonesian cities since 2000",
    license="CC-BY-4.0",
    keywords=["weather and climate", "earth and nature", "environment", "cities and urban areas", "asia", "time series analysis"],
    tables=TABLES,
    sources=(
        "Open-Meteo Historical Weather API (https://open-meteo.com/en/docs/historical-weather-api), CC BY 4.0; "
        "underlying data: ECMWF ERA5/ERA5-Land reanalysis (Copernicus Climate Change Service) and IFS. "
        "Collected daily by https://github.com/daniel766hi/kaggle-compe"
    ),
    make_fetchers=make_fetchers,
    describe=describe,
    derive=derive,
    cover=ASSETS / "idn-weather-cover.png",
)
