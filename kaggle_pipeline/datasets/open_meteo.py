"""Shared code for the Open-Meteo datasets (air quality and weather for Indonesian cities).

Open-Meteo's free tier allows about 10,000 "calls" a day, and a request counts as several
calls when it asks for more than 2 weeks of data or more than 10 variables. Full history
for 31 cities is too much for one day, so each run:

1. fetches the recent window for every city (cheap, always done first), then
2. spends the rest of its budget extending each city's history backwards, oldest data last.

The history therefore fills up over a few runs, and later runs only fetch the recent window.
"""

import logging
import math
import re
import time
from collections import deque
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd
import requests

from ..http import get_json, make_session

log = logging.getLogger(__name__)

# city, province, island, latitude, longitude
CITIES = [
    ("Jakarta", "DKI Jakarta", "Java", -6.2088, 106.8456),
    ("Surabaya", "Jawa Timur", "Java", -7.2575, 112.7521),
    ("Bandung", "Jawa Barat", "Java", -6.9175, 107.6191),
    ("Semarang", "Jawa Tengah", "Java", -6.9667, 110.4167),
    ("Yogyakarta", "DI Yogyakarta", "Java", -7.7956, 110.3695),
    ("Malang", "Jawa Timur", "Java", -7.9666, 112.6326),
    ("Serang", "Banten", "Java", -6.1200, 106.1503),
    ("Medan", "Sumatera Utara", "Sumatra", 3.5952, 98.6722),
    ("Palembang", "Sumatera Selatan", "Sumatra", -2.9761, 104.7754),
    ("Padang", "Sumatera Barat", "Sumatra", -0.9471, 100.4172),
    ("Pekanbaru", "Riau", "Sumatra", 0.5071, 101.4478),
    ("Bandar Lampung", "Lampung", "Sumatra", -5.3971, 105.2668),
    ("Banda Aceh", "Aceh", "Sumatra", 5.5483, 95.3238),
    ("Jambi", "Jambi", "Sumatra", -1.6101, 103.6131),
    ("Batam", "Kepulauan Riau", "Sumatra", 1.0456, 104.0305),
    ("Pontianak", "Kalimantan Barat", "Kalimantan", -0.0263, 109.3425),
    ("Banjarmasin", "Kalimantan Selatan", "Kalimantan", -3.3186, 114.5944),
    ("Samarinda", "Kalimantan Timur", "Kalimantan", -0.5022, 117.1536),
    ("Balikpapan", "Kalimantan Timur", "Kalimantan", -1.2379, 116.8529),
    ("Palangka Raya", "Kalimantan Tengah", "Kalimantan", -2.2161, 113.9135),
    ("Makassar", "Sulawesi Selatan", "Sulawesi", -5.1477, 119.4327),
    ("Manado", "Sulawesi Utara", "Sulawesi", 1.4748, 124.8421),
    ("Palu", "Sulawesi Tengah", "Sulawesi", -0.8917, 119.8707),
    ("Kendari", "Sulawesi Tenggara", "Sulawesi", -3.9985, 122.5129),
    ("Denpasar", "Bali", "Bali & Nusa Tenggara", -8.6705, 115.2126),
    ("Mataram", "Nusa Tenggara Barat", "Bali & Nusa Tenggara", -8.5833, 116.1167),
    ("Kupang", "Nusa Tenggara Timur", "Bali & Nusa Tenggara", -10.1772, 123.6070),
    ("Ambon", "Maluku", "Maluku", -3.6954, 128.1814),
    ("Ternate", "Maluku Utara", "Maluku", 0.7893, 127.3800),
    ("Jayapura", "Papua", "Papua", -2.5337, 140.7181),
    ("Sorong", "Papua Barat Daya", "Papua", -0.8762, 131.2558),
]
CITY_INFO = {c[0]: {"province": c[1], "island": c[2], "latitude": c[3], "longitude": c[4]} for c in CITIES}

BUDGET_UNITS = 4000  # per run; stays under the hourly limit (5,000) and leaves daily headroom
PER_MINUTE_UNITS = 500  # Open-Meteo allows 600 per minute
RANGE_ERROR = re.compile(r"from (\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})")


class RateLimited(Exception):
    """Open-Meteo's daily/hourly limit is used up; stop and continue on the next run."""


def _is_rate_limit(exc):
    resp = getattr(exc, "response", None)
    return getattr(resp, "status_code", None) == 429 or "limit exceeded" in (getattr(resp, "text", "") or "").lower()


@dataclass(frozen=True)
class Job:
    city: str
    start: date
    end: date
    backfill: bool

    def units(self, n_vars):
        days = (self.end - self.start).days + 1
        return math.ceil(days / 14) * math.ceil(n_vars / 10)


def _chunks(start, end, chunk_days, newest_first=True):
    out = []
    hi = end
    while hi >= start:
        lo = max(start, hi - timedelta(days=chunk_days - 1))
        out.append((lo, hi))
        hi = lo - timedelta(days=1)
    return out if newest_first else out[::-1]


def plan(coverage, cities, first_day, last_day, recent_days, chunk_days):
    """Decide which date ranges to request this run.

    coverage: {city: (earliest date, latest date)} already in the dataset.
    Returns recent-window jobs for every city first, then backfill jobs interleaved across
    cities (newest chunk of every city, then the next-newest, ...).
    """
    recent, backfill = [], []
    for city in cities:
        lo, hi = coverage.get(city, (None, None))
        if lo is None:
            per_city = _chunks(first_day, last_day, chunk_days)
            recent.append(Job(city, *per_city[0], backfill=False))
            backfill.append([Job(city, a, b, True) for a, b in per_city[1:]])
            continue
        # Re-fetch the recent window (values get revised) and any gap since the last run.
        recent_start = min(last_day - timedelta(days=recent_days - 1), hi + timedelta(days=1))
        recent += [Job(city, a, b, False) for a, b in _chunks(max(recent_start, lo), last_day, chunk_days)]
        if lo > first_day:
            backfill.append([Job(city, a, b, True) for a, b in _chunks(first_day, lo - timedelta(days=1), chunk_days)])
    interleaved = [job for round_ in _zip_longest(backfill) for job in round_]
    return recent + interleaved


def _zip_longest(lists):
    for i in range(max((len(x) for x in lists), default=0)):
        yield [x[i] for x in lists if i < len(x)]


def coverage_of(previous, date_col):
    if previous is None or previous.empty:
        return {}
    dates = previous[date_col].dt.date
    grouped = dates.groupby(previous["city"])
    return {city: (grouped.min()[city], grouped.max()[city]) for city in grouped.groups}


def request(session, url, params):
    """GET with Open-Meteo's date-range errors handled: if the range is partly outside what
    the API offers, retry once with the range clamped. Returns None if nothing is available."""
    try:
        return get_json(session, url, params)
    except requests.exceptions.HTTPError as exc:
        if _is_rate_limit(exc):
            raise RateLimited(exc.response.text) from exc
        if getattr(exc.response, "status_code", None) != 400:
            raise
        match = RANGE_ERROR.search(exc.response.text or "")
        if not match:
            raise
        allowed_lo, allowed_hi = (date.fromisoformat(d) for d in match.groups())
        lo = max(date.fromisoformat(params["start_date"]), allowed_lo)
        hi = min(date.fromisoformat(params["end_date"]), allowed_hi)
        if lo > hi:
            return None
        return get_json(session, url, {**params, "start_date": lo.isoformat(), "end_date": hi.isoformat()})


class Pacer:
    """Keeps request "units" under Open-Meteo's per-minute limit (600) by waiting when needed."""

    def __init__(self, per_minute=PER_MINUTE_UNITS, clock=time.monotonic, sleep=time.sleep):
        self.per_minute, self.clock, self.sleep = per_minute, clock, sleep
        self.window = deque()  # (timestamp, units)

    def wait_for(self, units):
        while True:
            now = self.clock()
            while self.window and now - self.window[0][0] >= 60:
                self.window.popleft()
            if sum(u for _, u in self.window) + units <= self.per_minute or not self.window:
                self.window.append((now, units))
                return
            self.sleep(60 - (now - self.window[0][0]) + 0.5)


def run_jobs(jobs, fetch_one, n_vars, budget=BUDGET_UNITS, pacer=None):
    """Execute jobs until the run's budget is spent or Open-Meteo's daily/hourly limit is hit.

    fetch_one(job) -> DataFrame or None. Recent-window jobs always run; a failing one is
    logged and skipped (the minimum-row check catches a source that is fully down).
    A per-minute limit is waited out; any other limit stops the run, keeping what was fetched.
    """
    pacer = pacer or Pacer()
    frames, spent, skipped = [], 0, 0
    for i, job in enumerate(jobs):
        cost = job.units(n_vars)
        if job.backfill and spent + cost > budget:
            skipped += 1
            continue
        df, stop = None, False
        for attempt in range(2):
            pacer.wait_for(cost)
            try:
                df = fetch_one(job)
                break
            except (RateLimited, requests.exceptions.RequestException) as exc:
                reason = str(exc) if isinstance(exc, RateLimited) else getattr(exc.response, "text", "") or str(exc)
                limited = isinstance(exc, RateLimited) or _is_rate_limit(exc)
                if limited and "minutely" in reason.lower() and attempt == 0:
                    log.info("Open-Meteo per-minute limit; waiting a minute")
                    pacer.sleep(61)
                    continue
                if limited:
                    log.warning("Open-Meteo limit reached (%s); continuing next run", reason.strip()[:120])
                    stop = True
                else:
                    log.warning("%s %s..%s failed: %s", job.city, job.start, job.end, exc)
                    stop = job.backfill  # keep what we have; the next run picks up from here
                break
        if stop:
            skipped += len(jobs) - i
            break
        spent += cost
        if df is not None and not df.empty:
            frames.append(df)
    log.info("Open-Meteo: spent ~%d units, %d requests left for later runs", spent, skipped)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def session():
    # Don't retry 429 here: Open-Meteo's daily limit won't lift within the retry window.
    return make_session(retry_statuses=(500, 502, 503, 504))


def with_city_columns(df, city):
    info = CITY_INFO[city]
    df.insert(0, "city", city)
    df.insert(1, "province", info["province"])
    df.insert(2, "island", info["island"])
    return df


def cities_frame():
    return pd.DataFrame(
        [{"city": c, "province": p, "island": i, "latitude": la, "longitude": lo} for c, p, i, la, lo in CITIES]
    )
