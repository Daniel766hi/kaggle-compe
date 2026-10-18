"""Indonesia fire hotspots: NASA FIRMS active-fire detections from the VIIRS satellites.

FIRMS publishes each satellite's detections in two forms: near-real-time (NRT, available within
hours) and standard processing (SP, the final archive, a few months behind). Days the archive
covers are fetched from it; newer days from NRT, and those are replaced by archive data once it
exists. Requests cover a bounding box around Indonesia; each detection is then given the province
it falls in (geoBoundaries outlines), and detections outside Indonesia (Malaysia, Timor-Leste,
Papua New Guinea) are dropped.

The history back to 2012 takes several runs: each run fetches recent days first, then older ones
until a time budget is spent.
"""

import io
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..http import USER_AGENT
from ..schema import Column, DatasetSpec, Table, files_markdown

log = logging.getLogger(__name__)

ASSETS = Path(__file__).resolve().parents[2] / "assets"
FIRMS = "https://firms.modaps.eosdis.nasa.gov/api"
BBOX = "94.5,-11.5,141.5,6.5"  # west,south,east,north around Indonesia
DAYS_PER_REQUEST = 5  # FIRMS's maximum day range per request
GEOBOUNDARIES = "https://www.geoboundaries.org/api/current/gbOpen/IDN/ADM1/"
COAST_TOLERANCE_DEG = 0.02  # detections this close to a province outline (about 2 km) still count
RECENT_DAYS = 10  # always refetched: NRT data for the last days is still being completed
BUDGET_S = int(os.environ.get("FIRMS_BUDGET_S") or 45 * 60)
WORKERS = 3

# satellite name -> (first day, FIRMS source for the archive, FIRMS source for near real time)
SATELLITES = {
    "Suomi NPP": (date(2012, 1, 20), "VIIRS_SNPP_SP", "VIIRS_SNPP_NRT"),
    "NOAA-20": (date(2018, 4, 1), "VIIRS_NOAA20_SP", "VIIRS_NOAA20_NRT"),
}
CONFIDENCE = {"l": "low", "n": "nominal", "h": "high"}

HOTSPOTS = Table(
    name="hotspots",
    kind="history",  # the fetcher returns the whole table, so archive rows can replace NRT rows
    fmt="parquet",
    description="One row per active-fire detection in Indonesia by the VIIRS sensors (375 m pixels).",
    key=("satellite", "acq_datetime", "latitude", "longitude"),
    min_rows=1000,
    max_shrink=0.02,  # replacing NRT rows by the archive can change a few overpass times
    columns=[
        Column("acq_date", "datetime", "Date of the satellite overpass (UTC)"),
        Column("acq_datetime", "datetime", "Date and time of the overpass (UTC)"),
        Column("satellite", "string", "Suomi NPP or NOAA-20"),
        Column("latitude", "number", "Centre of the 375 m fire pixel"),
        Column("longitude", "number", "Centre of the 375 m fire pixel"),
        Column("province", "string", "Province the pixel falls in (geoBoundaries ADM1)"),
        Column("confidence", "string", "low, nominal or high (FIRMS detection confidence)"),
        Column("frp", "number", "Fire radiative power in MW: how intense the fire was"),
        Column("bright_ti4", "number", "Brightness temperature, I-4 channel (kelvin)"),
        Column("bright_ti5", "number", "Brightness temperature, I-5 channel (kelvin)"),
        Column("daynight", "string", "D = daytime overpass, N = night-time overpass"),
        Column("processing", "string", "SP = final archive, NRT = near real time (replaced by SP later)"),
    ],
)

DAILY_PROVINCE = Table(
    name="daily_province",
    kind="derived",
    description="Per day and province: hotspots detected by Suomi NPP (consistent since 2012) and by NOAA-20.",
    key=("date", "province"),
    min_rows=0,
    columns=[
        Column("date", "datetime", "Date (UTC)"),
        Column("province", "string", "Province"),
        Column("hotspots_snpp", "integer", "Detections by Suomi NPP (use this for trends since 2012)"),
        Column("hotspots_noaa20", "integer", "Detections by NOAA-20 (from 2018)"),
        Column("high_confidence_snpp", "integer", "Suomi NPP detections with high confidence"),
        Column("frp_sum_snpp", "number", "Total fire radiative power of Suomi NPP detections (MW)"),
    ],
)

MONTHLY = Table(
    name="monthly_province",
    kind="derived",
    description="Per month and province: Suomi NPP hotspots, high-confidence hotspots and total FRP.",
    key=("month", "province"),
    min_rows=0,
    columns=[
        Column("month", "datetime", "First day of the month"),
        Column("province", "string", "Province"),
        Column("hotspots", "integer", "Suomi NPP detections"),
        Column("high_confidence", "integer", "Suomi NPP detections with high confidence"),
        Column("frp_sum", "number", "Total fire radiative power (MW)"),
    ],
)

TABLES = [HOTSPOTS, DAILY_PROVINCE, MONTHLY]

# ---------- FIRMS ----------


def make_session():
    session = requests.Session()
    retry = Retry(total=5, backoff_factor=3, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=("GET",))
    session.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=WORKERS * 2))
    session.headers["User-Agent"] = USER_AGENT
    return session


def map_key():
    key = os.environ.get("FIRMS_MAP_KEY", "").strip()
    if not key:
        raise RuntimeError("Set FIRMS_MAP_KEY (free from https://firms.modaps.eosdis.nasa.gov/api/map_key/)")
    return key


def archive_end(session, key):
    """Last day each archive (SP) source covers, from FIRMS's data availability list."""
    resp = session.get(f"{FIRMS}/data_availability/csv/{key}/ALL", timeout=60)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    return {row.data_id: pd.Timestamp(row.max_date).date() for row in df.itertuples()}


def fetch_chunk(session, key, source, start):
    """Detections in the bounding box for DAYS_PER_REQUEST days starting at `start`."""
    url = f"{FIRMS}/area/csv/{key}/{source}/{BBOX}/{DAYS_PER_REQUEST}/{start:%Y-%m-%d}"
    resp = session.get(url, timeout=180)
    resp.raise_for_status()
    text = resp.text.strip()
    if not text or "," not in text.splitlines()[0]:
        raise RuntimeError(f"FIRMS answered {source} {start}: {text[:200]}")
    return pd.read_csv(io.StringIO(text), dtype={"acq_time": str, "confidence": str, "version": str})


def tidy(raw, satellite, processing):
    hhmm = raw["acq_time"].astype(str).str.zfill(4)
    return pd.DataFrame({
        "acq_date": pd.to_datetime(raw["acq_date"]),
        "acq_datetime": pd.to_datetime(raw["acq_date"] + " " + hhmm.str[:2] + ":" + hhmm.str[2:]),
        "satellite": satellite,
        "latitude": raw["latitude"],
        "longitude": raw["longitude"],
        "confidence": raw["confidence"].astype(str).str.lower().map(CONFIDENCE),
        "frp": raw["frp"],
        "bright_ti4": raw["bright_ti4"],
        "bright_ti5": raw["bright_ti5"],
        "daynight": raw["daynight"],
        "processing": processing,
    })


def plan(previous, satellites, archive_ends, last_day, recent_days=RECENT_DAYS):
    """Chunks to fetch as (satellite, source, processing, start): recent NRT chunks, then older ones,
    newest first.

    An older chunk is needed when none of its days has data from the right source: missing days, or
    days only covered by NRT data that the archive now covers. (Gas flares and volcanoes are detected
    every few days, so a fetched chunk always has rows.) Chunks are fixed 5-day windows counted from
    the satellite's first day, so all runs agree on their boundaries.
    """
    have = {}
    if previous is not None and not previous.empty:
        for (sat, proc), days in previous.groupby(["satellite", "processing"])["acq_date"]:
            have[(sat, proc)] = set(pd.to_datetime(days).dt.date)
    recent, older = [], []
    for sat, (first, sp_source, nrt_source) in satellites.items():
        sp_end = archive_ends.get(sp_source, first - timedelta(days=1))
        start = first + timedelta(days=((last_day - first).days // DAYS_PER_REQUEST) * DAYS_PER_REQUEST)
        while start >= first:
            days = [start + timedelta(days=i) for i in range(DAYS_PER_REQUEST)]
            in_archive = days[-1] <= sp_end
            proc, source = ("SP", sp_source) if in_archive else ("NRT", nrt_source)
            if not in_archive and (last_day - start).days < recent_days:
                recent.append((sat, source, proc, start))
            elif not any(d in have.get((sat, proc), ()) for d in days):
                older.append((sat, source, proc, start))
            start -= timedelta(days=DAYS_PER_REQUEST)
    return recent, older


# ---------- provinces ----------


class Provinces:
    """Point-in-polygon lookup for Indonesian provinces (geoBoundaries ADM1, CC BY 4.0)."""

    def __init__(self, names, geometries):
        import shapely
        self.names = np.asarray(names, dtype=object)
        self.geometries = list(geometries)
        self.tree = shapely.STRtree(self.geometries)

    @classmethod
    def download(cls, session):
        import shapely
        meta = session.get(GEOBOUNDARIES, timeout=60)
        meta.raise_for_status()
        url = meta.json()["simplifiedGeometryGeoJSON"]
        geo = session.get(url, timeout=120)
        geo.raise_for_status()
        features = geo.json()["features"]
        names = [f["properties"]["shapeName"] for f in features]
        geometries = [shapely.geometry.shape(f["geometry"]) for f in features]
        log.info("geoBoundaries: %d provinces", len(names))
        return cls(names, geometries)

    def lookup(self, lon, lat):
        import shapely
        points = shapely.points(np.asarray(lon, dtype=float), np.asarray(lat, dtype=float))
        result = np.full(len(points), None, dtype=object)
        if len(points) == 0:
            return result
        pt_idx, poly_idx = self.tree.query(points, predicate="within")
        result[pt_idx] = self.names[poly_idx]
        missing = np.flatnonzero(pd.isna(result))
        if len(missing):
            pt2, poly2 = self.tree.query_nearest(points[missing], max_distance=COAST_TOLERANCE_DEG)
            result[missing[pt2]] = self.names[poly2]
        return result


def fetch_hotspots(session, previous, last_day, provinces=None, key=None, budget_s=BUDGET_S, clock=time.monotonic):
    key = key or map_key()
    ends = archive_end(session, key)
    log.info("FIRMS archive (SP) ends: %s", {s[1]: ends.get(s[1]) for s in SATELLITES.values()})
    recent, older = plan(previous, SATELLITES, ends, last_day)
    log.info("FIRMS: %d recent chunks, %d older chunks to fetch", len(recent), len(older))
    provinces = provinces or Provinces.download(session)
    frames, failed = [], []

    def one(job):
        sat, source, proc, start = job
        try:
            raw = fetch_chunk(session, key, source, start)
            return job, tidy(raw, sat, proc) if len(raw) else pd.DataFrame(columns=HOTSPOTS.column_names)
        except Exception as exc:  # noqa: BLE001 - one bad chunk must not stop the others
            return job, exc

    def collect(results):
        for job, result in results:
            if isinstance(result, Exception):
                failed.append(job)
                log.warning("FIRMS %s %s: %s", job[1], job[3], result)
            else:
                frames.append(result)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        collect(pool.map(one, recent))
        deadline = clock() + budget_s
        step = WORKERS * 4
        for i in range(0, len(older), step):
            if clock() > deadline:
                log.info("FIRMS: time budget spent; %d chunks left for the next runs", len(older) - i)
                break
            collect(pool.map(one, older[i:i + step]))
            if (i // step) % 10 == 0:
                log.info("FIRMS: %d / %d older chunks", min(i + step, len(older)), len(older))
    if not frames:
        raise RuntimeError(f"no FIRMS data could be downloaded ({len(failed)} chunks failed)")
    filled = [f for f in frames if not f.empty]
    new = pd.concat(filled, ignore_index=True) if filled else pd.DataFrame(columns=HOTSPOTS.column_names)
    new["province"] = provinces.lookup(new["longitude"], new["latitude"])
    outside = new["province"].isna()
    new = new[~outside]
    log.info("FIRMS: %d detections in Indonesia fetched (%d outside dropped), %d chunks failed",
             len(new), int(outside.sum()), len(failed))
    if previous is None or previous.empty:
        return new
    # The whole table is returned: previous rows, minus those the new data replaces (same satellite
    # and day: refetched NRT days, and NRT days now covered by the archive), plus the new rows.
    fetched = set(zip(new["satellite"], new["acq_date"]))
    replaced = pd.Series([k in fetched for k in zip(previous["satellite"], previous["acq_date"])],
                         index=previous.index)
    log.info("FIRMS: %d earlier rows replaced", int(replaced.sum()))
    return pd.concat([previous[~replaced], new], ignore_index=True)


# ---------- derived ----------


def summaries(fires):
    if fires is None or fires.empty:
        return (pd.DataFrame(columns=DAILY_PROVINCE.column_names), pd.DataFrame(columns=MONTHLY.column_names))
    snpp = fires[fires["satellite"] == "Suomi NPP"]
    noaa = fires[fires["satellite"] == "NOAA-20"]
    daily = pd.concat([
        snpp.groupby(["acq_date", "province"]).size().rename("hotspots_snpp"),
        noaa.groupby(["acq_date", "province"]).size().rename("hotspots_noaa20"),
        snpp[snpp["confidence"] == "high"].groupby(["acq_date", "province"]).size().rename("high_confidence_snpp"),
        snpp.groupby(["acq_date", "province"])["frp"].sum().rename("frp_sum_snpp"),
    ], axis=1).fillna({"hotspots_snpp": 0, "hotspots_noaa20": 0, "high_confidence_snpp": 0})
    daily = daily.reset_index().rename(columns={"acq_date": "date"})
    month = snpp.assign(month=snpp["acq_date"].dt.to_period("M").dt.to_timestamp())
    monthly = month.groupby(["month", "province"]).agg(
        hotspots=("frp", "size"),
        high_confidence=("confidence", lambda s: int((s == "high").sum())),
        frp_sum=("frp", "sum"),
    ).reset_index()
    return daily[DAILY_PROVINCE.column_names], monthly


def derive(frames):
    daily, monthly = summaries(frames.get("hotspots"))
    return {"daily_province": daily, "monthly_province": monthly}


def make_fetchers(_, snapshot_date):
    last_day = snapshot_date.date() - timedelta(days=1)
    return {"hotspots": lambda previous: fetch_hotspots(make_session(), previous, last_day)}


# ---------- description ----------


def coverage_markdown(frames):
    hotspots = frames.get("hotspots") if frames else None
    if hotspots is None or hotspots.empty:
        return "(computed when the dataset is built)"
    fires = hotspots
    lines = ["| Satellite | Detections | First day | Last day |", "|---|---|---|---|"]
    for sat, g in fires.groupby("satellite"):
        lines.append(f"| {sat} | {len(g):,} | {g['acq_date'].min():%Y-%m-%d} | {g['acq_date'].max():%Y-%m-%d} |")
    return "\n".join(lines)


def describe(snapshot_date, tables_written, frames=None):
    return "\n".join([
        "Every **active fire detected by satellite in Indonesia** since 2012, from NASA's Fire Information for "
        "Resource Management System (FIRMS), with the province of each detection. Updated daily: use it to track "
        "forest and land fires (*karhutla*) as they happen and to compare fire seasons such as 2015, 2019, 2023 "
        "and 2026.",
        "",
        "## Why this dataset",
        "",
        "- **Ready to analyse**: FIRMS's raw downloads cover a rectangle and mix countries; here each detection "
        "has its Indonesian province, and detections in Malaysia, Timor-Leste and Papua New Guinea are removed.",
        "- **Long and consistent**: Suomi NPP has observed since January 2012, so years can be compared; NOAA-20 "
        "(from 2018) adds a second look each day.",
        "- **Daily and monthly summaries per province** for quick time-series work.",
        "- **Joins well** with the [Indonesia air quality](https://www.kaggle.com/datasets/danielaijdkx/"
        "indonesia-air-quality-hourly-pm25) and [weather](https://www.kaggle.com/datasets/danielaijdkx/"
        "indonesia-daily-weather-31-cities) datasets (smoke and PM2.5, dry spells and fires).",
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
        "- A detection is a 375 m pixel that was hotter than its surroundings at the satellite's overpass "
        "(about 1:30 pm and 1:30 am local time). One fire can produce many detections, and fires hidden by "
        "cloud or smoke, or burning between overpasses, are missed. Use counts to compare places and seasons.",
        "- Each satellite sees the same fires, so **do not add the two satellites' counts**: use Suomi NPP "
        "(`hotspots_snpp`) for trends since 2012.",
        "- `frp` (fire radiative power) measures intensity; peat fires often smoulder with low FRP but last long.",
        "- `processing`: recent days come from near-real-time data (NRT) and are replaced by the final archive "
        "(SP) once NASA publishes it, a few months later.",
        "",
        "## Updates",
        "",
        f"Updated daily. Last update: {snapshot_date:%Y-%m-%d} (UTC).",
        "",
        "## Sources and license",
        "",
        "- Fire detections: NASA FIRMS (https://firms.modaps.eosdis.nasa.gov). We acknowledge the use of data "
        "from NASA's Fire Information for Resource Management System (FIRMS), part of NASA's Earth Science Data "
        "and Information System (ESDIS). VIIRS 375 m active fire product (VNP14IMG / VJ114IMG).",
        "- Province outlines: [geoBoundaries](https://www.geoboundaries.org) (Runfola et al. 2020), CC BY 4.0.",
        "",
        "This dataset is shared under CC BY 4.0: credit NASA FIRMS and geoBoundaries when you use it.",
    ])


SPEC = DatasetSpec(
    name="idn-fires",
    slug="indonesia-fire-hotspots-nasa-firms",
    title="Indonesia Fire Hotspots (NASA FIRMS, daily)",
    subtitle="Every satellite-detected fire in Indonesia since 2012, by province, updated daily",
    license="CC-BY-4.0",
    keywords=["environment", "earth and nature", "asia", "geography", "time series analysis"],
    tables=TABLES,
    sources=(
        "NASA FIRMS (https://firms.modaps.eosdis.nasa.gov), VIIRS 375 m active fires (Suomi NPP, NOAA-20); "
        "geoBoundaries IDN ADM1 (https://www.geoboundaries.org), CC BY 4.0. "
        "Built daily by https://github.com/daniel766hi/kaggle-compe"
    ),
    make_fetchers=make_fetchers,
    derive=derive,
    describe=describe,
    cover=ASSETS / "idn-fires-cover.png",
)
