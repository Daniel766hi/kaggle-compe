"""Indonesia earthquakes: the USGS ComCat catalogue for a box around Indonesia, since 1900.

The first run downloads the whole history (one request per period, split further when a period
holds more than USGS's 20,000-event limit). Later runs ask USGS for every event *updated* since
the last run, wherever it happened in time: new quakes, and revisions of older ones (reviewed
magnitudes and locations). When USGS merges two events, the surviving one lists the other's id in
`ids`, and the old row is dropped.

Each epicentre gets the nearest land: an Indonesian province (geoBoundaries ADM1) or a neighbouring
country (geoBoundaries ADM0), with the distance to it (0 when the epicentre is on land).
"""

import logging
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from ..http import make_session as base_session
from ..schema import Column, DatasetSpec, Table, files_markdown
from .idn_fires import GEOBOUNDARIES

log = logging.getLogger(__name__)

ASSETS = Path(__file__).resolve().parents[2] / "assets"
USGS = "https://earthquake.usgs.gov/fdsnws/event/1"
BOX = {"minlatitude": -12.5, "maxlatitude": 7.5, "minlongitude": 93.5, "maxlongitude": 142.5}
MAX_EVENTS = 20000  # USGS refuses queries that would return more
FIRST_YEAR = 1900
# geoBoundaries ADM0 of the countries whose land lies inside the box (besides Indonesia).
NEIGHBOURS = {"MYS": "Malaysia", "PHL": "Philippines", "PNG": "Papua New Guinea", "TLS": "Timor-Leste",
              "AUS": "Australia", "SGP": "Singapore", "BRN": "Brunei"}
KM_PER_DEG = 111.32  # good enough near the equator for "distance to land"
REVISION_OVERLAP = timedelta(days=2)

# Aftershock sequences (derived table): mainshocks of M5.5+, aftershocks of M4.5+ (about the
# magnitude the global catalogue records completely in Indonesia since the 1990s).
MAINSHOCK_MIN_MAG = 5.5
AFTERSHOCK_MIN_MAG = 4.5
SEQUENCES_FROM = pd.Timestamp("1990-01-01")


def search_radius_km(mag):
    """Radius around a mainshock that counts as its aftershock zone: the rupture length from
    Wells & Coppersmith (1994), log10 L = -2.44 + 0.59 M, but at least 75 km (location errors)."""
    return np.maximum(75.0, 10 ** (-2.44 + 0.59 * np.asarray(mag, dtype=float)))


EVENTS = Table(
    name="earthquakes",
    kind="history",  # the fetcher returns the whole table: revised events replace their old rows
    description="One row per seismic event in the USGS catalogue for Indonesia and its surroundings, since 1900.",
    key=("id",),
    min_rows=1000,
    max_shrink=0.01,  # USGS occasionally merges duplicate events or deletes false ones
    columns=[
        Column("id", "string", "USGS event id (the preferred one; see ids)"),
        Column("time", "datetime", "Origin time (UTC)"),
        Column("time_wib", "datetime", "Origin time in Western Indonesia Time (UTC+7)"),
        Column("latitude", "number", "Epicentre latitude"),
        Column("longitude", "number", "Epicentre longitude"),
        Column("depth_km", "number", "Hypocentre depth in km"),
        Column("mag", "number", "Magnitude"),
        Column("mag_type", "string", "Magnitude type: mww/mw (moment), mb (body wave), ms, ml, ..."),
        Column("place", "string", "USGS's description of the location"),
        Column("country", "string", "Indonesia or the neighbouring country with the nearest land"),
        Column("province", "string", "Nearest Indonesian province (when country is Indonesia)"),
        Column("km_to_land", "number", "Approximate distance from the epicentre to that land (0 = on land)"),
        Column("type", "string", "earthquake, or another event type (e.g. volcanic eruption)"),
        Column("status", "string", "reviewed by a seismologist, or automatic"),
        Column("tsunami", "integer", "1 if USGS flagged the event as large and oceanic (not proof of a tsunami)"),
        Column("felt", "integer", "Number of 'Did You Feel It?' reports"),
        Column("cdi", "number", "Maximum reported intensity from 'Did You Feel It?' (MMI scale)"),
        Column("mmi", "number", "Maximum estimated instrumental intensity (ShakeMap, MMI scale)"),
        Column("alert", "string", "PAGER alert level for impact: green, yellow, orange or red"),
        Column("sig", "integer", "USGS significance score (0-1000+), from magnitude, felt reports and impact"),
        Column("net", "string", "Network that contributed the preferred solution"),
        Column("nst", "integer", "Number of stations used to locate the event"),
        Column("gap", "number", "Largest azimuthal gap between stations, degrees"),
        Column("dmin", "number", "Distance to the nearest station, degrees"),
        Column("rms", "number", "Root-mean-square travel time residual, seconds"),
        Column("ids", "string", "All ids of this event in the catalogue, comma-separated"),
        Column("updated", "datetime", "When USGS last updated the event (UTC)"),
    ],
)

MONTHLY = Table(
    name="monthly_province",
    kind="derived",
    description="Per month and Indonesian province: earthquakes by magnitude band and the largest magnitude.",
    key=("month", "province"),
    min_rows=0,
    columns=[
        Column("month", "datetime", "First day of the month (UTC)"),
        Column("province", "string", "Nearest Indonesian province"),
        Column("quakes_m45", "integer", "Earthquakes of magnitude 4.5 or more"),
        Column("quakes_m5", "integer", "Earthquakes of magnitude 5 or more"),
        Column("quakes_m6", "integer", "Earthquakes of magnitude 6 or more"),
        Column("shallow_m5", "integer", "Earthquakes of magnitude 5 or more shallower than 70 km"),
        Column("max_mag", "number", "Largest magnitude"),
    ],
)

SEQUENCES = Table(
    name="aftershock_sequences",
    kind="derived",
    description="Every M5.5+ earthquake since 1990 with the M4.5+ aftershocks that followed it nearby.",
    key=("mainshock_id",),
    min_rows=0,
    columns=[
        Column("mainshock_id", "string", "USGS id of the M5.5+ earthquake"),
        Column("time", "datetime", "Origin time (UTC)"),
        Column("latitude", "number", "Epicentre latitude"),
        Column("longitude", "number", "Epicentre longitude"),
        Column("depth_km", "number", "Depth in km"),
        Column("mag", "number", "Magnitude"),
        Column("mag_type", "string", "Magnitude type"),
        Column("country", "string", "Indonesia or the neighbouring country with the nearest land"),
        Column("province", "string", "Nearest Indonesian province (when country is Indonesia)"),
        Column("radius_km", "number", "Aftershock zone radius: rupture length (Wells & Coppersmith), at least 75 km"),
        Column("prior_m45_30d", "integer", "M4.5+ quakes within the radius in the 30 days before"),
        Column("prior_larger_30d", "boolean", "Within 30 days after a larger quake, inside that quake's aftershock zone"),
        Column("aftershocks_m45_1d", "integer", "M4.5+ quakes within the radius in the first 24 hours after"),
        Column("aftershocks_m5_1d", "integer", "M5+ quakes within the radius in the first 24 hours after"),
        Column("aftershocks_m45_7d", "integer", "M4.5+ quakes within the radius in the 7 days after"),
        Column("aftershocks_m5_7d", "integer", "M5+ quakes within the radius in the 7 days after"),
        Column("max_aftershock_mag_7d", "number", "Largest of those within 7 days (empty if none)"),
        Column("complete_7d", "boolean", "The 7 days after the quake are fully in the catalogue"),
    ],
)

TABLES = [EVENTS, MONTHLY, SEQUENCES]

# ---------- USGS ----------


def make_session():
    return base_session()


def usgs_params(**extra):
    return {"format": "geojson", "orderby": "time-asc", **BOX, **extra}


def count_events(session, start, end):
    resp = session.get(f"{USGS}/count", params=usgs_params(starttime=start.isoformat(), endtime=end.isoformat()),
                       timeout=120)
    resp.raise_for_status()
    return int(resp.json()["count"])


def query(session, **params):
    resp = session.get(f"{USGS}/query", params=usgs_params(limit=MAX_EVENTS, **params), timeout=300)
    if resp.status_code != 200:
        raise RuntimeError(f"USGS HTTP {resp.status_code}: {resp.text.strip()[:200]}")
    return resp.json().get("features", [])


def fetch_period(session, start, end):
    """All events with start <= time < end, splitting the period while it holds too many."""
    n = count_events(session, start, end)
    if n == 0:
        return []
    if n >= MAX_EVENTS and (end - start) > timedelta(days=1):
        middle = start + (end - start) / 2
        return fetch_period(session, start, middle) + fetch_period(session, middle, end)
    return query(session, starttime=start.isoformat(), endtime=end.isoformat())


def periods(first_year, last_day):
    """The history in request-sized periods: 1900-1972 together (sparse), then single years."""
    yield pd.Timestamp(f"{first_year}-01-01"), pd.Timestamp("1973-01-01")
    for year in range(1973, last_day.year + 1):
        yield pd.Timestamp(f"{year}-01-01"), min(pd.Timestamp(f"{year + 1}-01-01"), pd.Timestamp(last_day) + pd.Timedelta(days=1))


def to_frame(features):
    rows = []
    for f in features:
        p = f.get("properties") or {}
        lon, lat, depth = (list((f.get("geometry") or {}).get("coordinates") or []) + [None] * 3)[:3]
        rows.append({
            "id": f.get("id"), "time": p.get("time"), "latitude": lat, "longitude": lon, "depth_km": depth,
            "mag": p.get("mag"), "mag_type": p.get("magType"), "place": p.get("place"), "type": p.get("type"),
            "status": p.get("status"), "tsunami": p.get("tsunami"), "felt": p.get("felt"), "cdi": p.get("cdi"),
            "mmi": p.get("mmi"), "alert": p.get("alert"), "sig": p.get("sig"), "net": p.get("net"),
            "nst": p.get("nst"), "gap": p.get("gap"), "dmin": p.get("dmin"), "rms": p.get("rms"),
            "ids": (p.get("ids") or "").strip(","), "updated": p.get("updated"),
        })
    df = pd.DataFrame(rows, columns=[c.name for c in EVENTS.columns if c.name not in ("time_wib", "country",
                                                                                     "province", "km_to_land")])
    for col in ("time", "updated"):
        df[col] = pd.to_datetime(pd.to_numeric(df[col], errors="coerce"), unit="ms")
    df["time_wib"] = df["time"] + pd.Timedelta(hours=7)
    return df


def merge_revisions(previous, new):
    """previous rows, minus those that new rows replace (same id, or an id now merged into a new
    event's ids), plus the new rows."""
    if previous is None or previous.empty:
        return new
    replaced_ids = set(new["id"])
    for ids in new["ids"].dropna():
        replaced_ids.update(i for i in ids.split(",") if i)
    keep = previous[~previous["id"].isin(replaced_ids)]
    return pd.concat([keep, new], ignore_index=True)


# ---------- nearest land ----------


class Land:
    """Nearest-land lookup over Indonesia's provinces and the neighbouring countries."""

    def __init__(self, names, countries, geometries):
        import shapely
        self.names = np.asarray(names, dtype=object)
        self.countries = np.asarray(countries, dtype=object)
        self.tree = shapely.STRtree(list(geometries))

    @classmethod
    def download(cls, session):
        import shapely
        names, countries, geometries = [], [], []

        def shapes(url):
            meta = session.get(url, timeout=60)
            meta.raise_for_status()
            geo = session.get(meta.json()["simplifiedGeometryGeoJSON"], timeout=180)
            geo.raise_for_status()
            return geo.json()["features"]

        for f in shapes(GEOBOUNDARIES):
            names.append(f["properties"]["shapeName"])
            countries.append("Indonesia")
            geometries.append(shapely.geometry.shape(f["geometry"]))
        for iso, country in NEIGHBOURS.items():
            try:
                features = shapes(GEOBOUNDARIES.replace("/IDN/ADM1/", f"/{iso}/ADM0/"))
            except Exception as exc:  # noqa: BLE001 - a missing neighbour only makes "nearest land" coarser
                log.warning("geoBoundaries %s: %s", iso, exc)
                continue
            for f in features:
                names.append(None)
                countries.append(country)
                geometries.append(shapely.geometry.shape(f["geometry"]))
        log.info("geoBoundaries: %d outlines", len(names))
        return cls(names, countries, geometries)

    def lookup(self, lon, lat):
        """(country, province or None, km to that land) for each point."""
        import shapely
        n = len(lon)
        country = np.full(n, None, dtype=object)
        province = np.full(n, None, dtype=object)
        km = np.full(n, np.nan)
        if n == 0:
            return country, province, km
        points = shapely.points(np.asarray(lon, dtype=float), np.asarray(lat, dtype=float))
        (pt, poly), dist = self.tree.query_nearest(points, return_distance=True, all_matches=False)
        country[pt] = self.countries[poly]
        province[pt] = self.names[poly]
        km[pt] = np.round(dist * KM_PER_DEG, 1)
        return country, province, km


def add_land(df, land):
    df = df.copy()
    ok = df["longitude"].notna() & df["latitude"].notna()
    country, province, km = land.lookup(df.loc[ok, "longitude"].to_numpy(), df.loc[ok, "latitude"].to_numpy())
    df.loc[ok, "country"], df.loc[ok, "province"], df.loc[ok, "km_to_land"] = country, province, km
    return df


def fetch_events(session, previous, last_day, land=None):
    """The whole table: the full history on the first run, then previous rows plus every event
    USGS added or updated since the last run."""
    if previous is None or previous.empty:
        features = []
        for start, end in periods(FIRST_YEAR, last_day):
            got = fetch_period(session, start, end)
            log.info("USGS %s to %s: %d events", start.date(), end.date(), len(got))
            features += got
        new = to_frame(features)
    else:
        since = pd.to_datetime(previous["updated"]).max() - REVISION_OVERLAP
        new = to_frame(query(session, updatedafter=since.isoformat(), starttime=f"{FIRST_YEAR}-01-01"))
        if len(new) >= MAX_EVENTS:
            raise RuntimeError("more than 20,000 updated events since the last run; rebuild from scratch")
        log.info("USGS: %d events added or updated since %s", len(new), since)
    new = new[new["time"] < pd.Timestamp(last_day) + pd.Timedelta(days=1)]
    land = land or Land.download(session)
    new = add_land(new, land)
    return merge_revisions(previous, new)


# ---------- derived ----------


def monthly(events):
    q = events[(events["country"] == "Indonesia") & (events["type"] == "earthquake") & (events["mag"] >= 4.5)]
    if q.empty:
        return pd.DataFrame(columns=MONTHLY.column_names)
    q = q.assign(month=q["time"].dt.to_period("M").dt.to_timestamp())
    out = q.groupby(["month", "province"]).agg(
        quakes_m45=("mag", "size"),
        quakes_m5=("mag", lambda m: int((m >= 5).sum())),
        quakes_m6=("mag", lambda m: int((m >= 6).sum())),
        max_mag=("mag", "max"),
    )
    shallow = q[(q["mag"] >= 5) & (q["depth_km"] < 70)].groupby(["month", "province"]).size()
    out["shallow_m5"] = shallow.reindex(out.index).fillna(0).astype(int)
    return out.reset_index()[MONTHLY.column_names]


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


def sequences(events, last_time=None):
    """For each M5.5+ earthquake since 1990: activity within its aftershock radius before and after."""
    q = events[(events["type"] == "earthquake") & events["mag"].notna() & events["time"].notna()]
    q = q.sort_values("time").reset_index(drop=True)
    if q.empty:
        return pd.DataFrame(columns=SEQUENCES.column_names)
    last_time = last_time if last_time is not None else q["time"].max()
    t = q["time"].to_numpy()
    lat, lon, mag = q["latitude"].to_numpy(), q["longitude"].to_numpy(), q["mag"].to_numpy()
    rows = []
    mains = q.index[(q["mag"] >= MAINSHOCK_MIN_MAG) & (q["time"] >= SEQUENCES_FROM)]
    for i in mains:
        radius = float(search_radius_km(mag[i]))
        lo = np.searchsorted(t, t[i] - np.timedelta64(30, "D"))
        hi = np.searchsorted(t, t[i] + np.timedelta64(7, "D"), side="right")
        idx = np.arange(lo, hi)
        idx = idx[idx != i]
        dist = haversine_km(lat[i], lon[i], lat[idx], lon[idx])
        near = idx[dist <= radius]
        before, after = near[t[near] < t[i]], near[t[near] > t[i]]
        # A larger earlier quake counts when this one lies within *its* (larger) aftershock zone.
        earlier_larger = (t[idx] < t[i]) & (mag[idx] > mag[i]) & (dist <= search_radius_km(mag[idx]))
        # Same-second duplicates or events listed at the mainshock time count as neither.
        prior_m45 = before[mag[before] >= AFTERSHOCK_MIN_MAG]
        after45 = after[mag[after] >= AFTERSHOCK_MIN_MAG]
        day1 = after45[t[after45] <= t[i] + np.timedelta64(1, "D")]
        after5 = after45[mag[after45] >= 5.0]
        row = q.loc[i]
        rows.append({
            "mainshock_id": row["id"], "time": row["time"], "latitude": row["latitude"],
            "longitude": row["longitude"], "depth_km": row["depth_km"], "mag": row["mag"],
            "mag_type": row["mag_type"], "country": row["country"], "province": row["province"],
            "radius_km": round(radius, 1), "prior_m45_30d": len(prior_m45),
            "prior_larger_30d": bool(earlier_larger.any()),
            "aftershocks_m45_1d": len(day1), "aftershocks_m5_1d": int((mag[day1] >= 5.0).sum()),
            "aftershocks_m45_7d": len(after45),
            "aftershocks_m5_7d": len(after5),
            "max_aftershock_mag_7d": float(mag[after45].max()) if len(after45) else np.nan,
            "complete_7d": bool(row["time"] + pd.Timedelta(days=7) <= last_time),
        })
    return pd.DataFrame(rows, columns=SEQUENCES.column_names)


def derive(frames):
    events = frames.get("earthquakes")
    if events is None or events.empty:
        return {"monthly_province": pd.DataFrame(columns=MONTHLY.column_names),
                "aftershock_sequences": pd.DataFrame(columns=SEQUENCES.column_names)}
    end = events["time"].max().normalize() + pd.Timedelta(days=1)
    return {"monthly_province": monthly(events), "aftershock_sequences": sequences(events, last_time=end)}


def make_fetchers(_, snapshot_date):
    last_day = snapshot_date.date() - timedelta(days=1)
    return {"earthquakes": lambda previous: fetch_events(make_session(), previous, last_day)}


# ---------- description ----------


def coverage_markdown(frames):
    events = frames.get("earthquakes") if frames else None
    if events is None or events.empty:
        return "(computed when the dataset is built)"
    q = events[events["type"] == "earthquake"]
    idn = q[q["country"] == "Indonesia"]
    lines = ["| | Events | First | Last |", "|---|---|---|---|",
             f"| All events in the box | {len(events):,} | {events['time'].min():%Y-%m-%d} | {events['time'].max():%Y-%m-%d} |"]
    for label, sub in [("Earthquakes nearest Indonesia, M4.5+", idn[idn["mag"] >= 4.5]),
                       ("Earthquakes nearest Indonesia, M6+", idn[idn["mag"] >= 6]),
                       ("Earthquakes nearest Indonesia, M7+", idn[idn["mag"] >= 7])]:
        if len(sub):
            lines.append(f"| {label} | {len(sub):,} | {sub['time'].min():%Y-%m-%d} | {sub['time'].max():%Y-%m-%d} |")
    return "\n".join(lines)


def describe(snapshot_date, tables_written, frames=None):
    return "\n".join([
        "Every **earthquake recorded in and around Indonesia** since 1900, from the U.S. Geological Survey's "
        "global catalogue (ComCat), with the nearest Indonesian province of each epicentre. Updated daily, "
        "including USGS's later revisions of magnitudes and locations.",
        "",
        "## Why this dataset",
        "",
        "- **Ready to analyse**: each epicentre has its nearest land (an Indonesian province or a neighbouring "
        "country) and the distance to it, so offshore quakes can be grouped by province.",
        "- **Impact fields** USGS adds for larger events: felt reports, ShakeMap intensity, the PAGER alert "
        "level and the tsunami flag.",
        "- **Aftershock sequences**: every M5.5+ quake since 1990 with what came before and after it nearby, "
        "ready for forecasting (see the [aftershock model](https://www.kaggle.com/models/danielaijdkx/"
        "indonesia-aftershock-forecast)).",
        "- **Monthly counts per province** for quick time-series work.",
        "",
        "## Files",
        "",
        files_markdown(tables_written),
        "",
        "## Coverage",
        "",
        coverage_markdown(frames),
        "",
        "The box spans 12.5°S to 7.5°N and 93.5°E to 142.5°E, so it also holds quakes nearer Malaysia, the "
        "southern Philippines, Timor-Leste, Papua New Guinea and Australia; `country` tells them apart.",
        "",
        "## How to read it",
        "",
        "- **Completeness**: a global catalogue records only the larger quakes in Indonesia. Since about 1990 "
        "it is close to complete from magnitude 4.5; earlier decades, and smaller magnitudes, are patchy. "
        "Compare years with `mag >= 4.5` (or higher before 1990). Indonesia's own agency, BMKG, records many "
        "more small quakes.",
        "- **Magnitudes** come in several types (`mag_type`); moment magnitude (`mww`, `mw...`) is the "
        "standard for large quakes.",
        "- `tsunami` = 1 means USGS flagged a large oceanic event so that people check tsunami warnings; it "
        "does not mean a tsunami happened.",
        "- `km_to_land` uses simplified outlines and is approximate (a few km).",
        "- In `aftershock_sequences`, rows with `prior_larger_30d` are themselves likely aftershocks of an "
        "earlier, larger quake; rows with `complete_7d` false are too recent to have a full week after them.",
        "",
        "## Updates",
        "",
        f"Updated daily. Last update: {snapshot_date:%Y-%m-%d} (UTC).",
        "",
        "## Sources and license",
        "",
        "- Earthquakes: U.S. Geological Survey, Earthquake Hazards Program, ANSS Comprehensive Catalog "
        "(ComCat), https://earthquake.usgs.gov/earthquakes/search/. USGS data are in the public domain.",
        "- Province and country outlines: [geoBoundaries](https://www.geoboundaries.org) (Runfola et al. "
        "2020), CC BY 4.0.",
        "",
        "This dataset is shared under CC BY 4.0: credit the USGS and geoBoundaries when you use it.",
    ])


SPEC = DatasetSpec(
    name="idn-quakes",
    slug="indonesia-earthquakes-usgs-daily",
    title="Indonesia Earthquakes since 1900 (USGS, daily)",
    subtitle="Every recorded earthquake in and around Indonesia, by province, updated daily",
    license="CC-BY-4.0",
    keywords=["earth and nature", "geography", "asia", "time series analysis", "data visualization"],
    tables=TABLES,
    sources=(
        "U.S. Geological Survey ANSS Comprehensive Catalog (https://earthquake.usgs.gov/fdsnws/event/1/), "
        "public domain; geoBoundaries IDN ADM1 and neighbours' ADM0 (https://www.geoboundaries.org), "
        "CC BY 4.0. Built daily by https://github.com/daniel766hi/kaggle-compe"
    ),
    make_fetchers=make_fetchers,
    derive=derive,
    describe=describe,
    cover=ASSETS / "idn-quakes-cover.png",
)
