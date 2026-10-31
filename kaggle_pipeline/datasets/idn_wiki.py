"""What Indonesia reads: the daily top 1,000 articles of Indonesian Wikipedia, since July 2015.

Source: the Wikimedia pageviews API (https://wikimedia.org/api/rest_v1/, data CC0). Three requests
kinds are used:
- the daily top-1,000 list of id.wikipedia (one request per day; the first run backfills 2015
  onwards, later runs add the missing days);
- the project's total daily views, by access method (four requests per run);
- for every "attention spike" (an article that jumps into the top 100 from outside the top 1,000),
  that article's daily views from 7 days before to 14 days after, so the whole rise and fall can be
  studied, including the days it was outside the top list. Spikes are fetched newest first, within
  a time budget; older ones are filled in by later runs.
"""

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

import numpy as np
import pandas as pd
from requests.adapters import HTTPAdapter

from ..http import make_session as base_session
from ..schema import Column, DatasetSpec, Table, files_markdown

log = logging.getLogger(__name__)

ASSETS = Path(__file__).resolve().parents[2] / "assets"
API = "https://wikimedia.org/api/rest_v1/metrics/pageviews"
PROJECT = "id.wikipedia.org"
FIRST_DAY = date(2015, 7, 1)  # first day the pageviews API covers
WORKERS = 6  # Wikimedia asks API clients to stay well below 100 requests per second
BUDGET_S = int(os.environ.get("WIKI_BUDGET_S") or 40 * 60)
ACCESS = ("all-access", "desktop", "mobile-web", "mobile-app")

# Spikes: an article in the day's top SPIKE_RANK that was outside the top 1,000 on each of the
# QUIET_DAYS before; its series covers BEFORE days before to AFTER days after.
SPIKE_RANK, QUIET_DAYS, BEFORE, AFTER = 100, 7, 7, 14
OFFSETS = list(range(-BEFORE, AFTER + 1))

# Namespaces (Indonesian and English names) whose pages are not encyclopedia articles.
NAMESPACES = {
    "istimewa", "special", "wikipedia", "wp", "berkas", "file", "gambar", "image", "kategori", "category",
    "pengguna", "user", "templat", "template", "bantuan", "help", "portal", "modul", "module", "mediawiki",
    "pembicaraan", "talk", "pembicaraan_pengguna", "user_talk", "wikipedia_bicara", "media", "topik", "topic",
    "draf", "draft",
}
NOT_ARTICLES = {"Halaman_Utama", "Main_Page", "-", "Undefined", "Wikipedia"}


def view_col(offset):
    return f"views_m{-offset}" if offset < 0 else ("views_d0" if offset == 0 else f"views_p{offset}")


TOP = Table(
    name="top_articles",
    kind="incremental",
    fmt="parquet",
    description="The 1,000 most-viewed pages of Indonesian Wikipedia each day since 1 July 2015.",
    key=("date", "article"),
    min_rows=0,
    columns=[
        Column("date", "datetime", "Day (UTC)"),
        Column("rank", "integer", "Rank that day (1 = most viewed)"),
        Column("article", "string", "Page title as in the URL (underscores for spaces)"),
        Column("views", "integer", "Views that day by people (all devices; automated traffic excluded)"),
        Column("is_article", "boolean", "False for the main page, search and other non-article pages"),
    ],
)

TOTALS = Table(
    name="daily_totals",
    kind="history",
    description="Total daily views of Indonesian Wikipedia by people, overall and by device.",
    key=("date",),
    min_rows=1000,
    columns=[
        Column("date", "datetime", "Day (UTC)"),
        Column("views", "integer", "All views by people"),
        Column("views_desktop", "integer", "Views from desktop browsers"),
        Column("views_mobile_web", "integer", "Views from mobile browsers"),
        Column("views_mobile_app", "integer", "Views from the Wikipedia apps"),
    ],
)

SERIES = Table(
    name="spike_series",
    kind="incremental",
    fmt="parquet",
    description="Daily views of each spiking article from 7 days before its spike to 14 days after.",
    key=("article", "spike_date", "day_offset"),
    min_rows=0,
    columns=[
        Column("article", "string", "Page title"),
        Column("spike_date", "datetime", "Day it jumped into the top 100"),
        Column("day_offset", "integer", "Days after the spike day (-7 to 14)"),
        Column("date", "datetime", "Day (UTC)"),
        Column("views", "integer", "Views by people that day (0 when the API lists none)"),
    ],
)

SPIKES = Table(
    name="attention_spikes",
    kind="derived",
    description="One row per attention spike, with daily views from 7 days before to 14 days after.",
    key=("article", "spike_date"),
    min_rows=0,
    columns=[
        Column("article", "string", "Page title"),
        Column("title", "string", "Page title with spaces"),
        Column("spike_date", "datetime", "Day it jumped into the top 100 (UTC)"),
        Column("spike_rank", "integer", "Its rank that day"),
        Column("weekday", "integer", "Day of the week of the spike (0 = Monday)"),
        *[Column(view_col(o), "integer", f"Views {abs(o)} day{'s' if abs(o) > 1 else ''} "
                 f"{'before' if o < 0 else 'after'} the spike day" if o else "Views on the spike day")
          for o in OFFSETS],
        Column("baseline_7d", "number", "Mean daily views over the 7 days before"),
        Column("next_7d", "integer", "Total views over the 7 days after the spike day"),
        Column("half_life_days", "number", "Days until daily views first fell to half the spike day (empty: not within 14)"),
    ],
)

MONTHLY = Table(
    name="monthly_top_articles",
    kind="derived",
    description="The 50 most-read articles of each month (summed over the days they were in the daily top 1,000).",
    key=("month", "rank"),
    min_rows=0,
    columns=[
        Column("month", "datetime", "First day of the month"),
        Column("rank", "integer", "Rank in the month"),
        Column("article", "string", "Page title"),
        Column("views_in_top_lists", "integer", "Views summed over the days it was in the top 1,000 (a lower bound)"),
        Column("days_in_top", "integer", "Days of the month it was in the top 1,000"),
        Column("best_rank", "integer", "Its best daily rank in the month"),
    ],
)

TABLES = [TOP, TOTALS, SERIES, SPIKES, MONTHLY]


def is_article(titles):
    titles = pd.Series(titles, dtype="string")
    prefix = titles.str.split(":", n=1).str[0].str.lower()
    namespaced = titles.str.contains(":", regex=False) & prefix.isin(NAMESPACES)
    return ~(namespaced | titles.isin(NOT_ARTICLES))


# ---------- API ----------


def make_session():
    """The shared session (retries on 429 and 5xx), with a connection pool for the parallel workers."""
    session = base_session()
    retry = session.get_adapter("https://").max_retries
    session.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=WORKERS * 2))
    return session


def fetch_top_day(session, day):
    """The day's top list as a DataFrame, or None if the API has no list for that day (yet)."""
    url = f"{API}/top/{PROJECT}/all-access/{day:%Y/%m/%d}"
    resp = session.get(url, timeout=60)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    items = resp.json().get("items") or []
    articles = items[0].get("articles", []) if items else []
    df = pd.DataFrame(articles, columns=["article", "views", "rank"])
    df["date"] = pd.Timestamp(day)
    return df


def fetch_totals(session, last_day):
    out = None
    for access in ACCESS:
        url = f"{API}/aggregate/{PROJECT}/{access}/user/daily/{FIRST_DAY:%Y%m%d}00/{last_day:%Y%m%d}00"
        resp = session.get(url, timeout=120)
        resp.raise_for_status()
        rows = [(pd.to_datetime(i["timestamp"][:8]), i["views"]) for i in resp.json().get("items", [])]
        name = "views" if access == "all-access" else f"views_{access.replace('-', '_')}"
        df = pd.DataFrame(rows, columns=["date", name])
        out = df if out is None else out.merge(df, on="date", how="outer")
    return out.sort_values("date")


def fetch_article_days(session, article, start, end):
    """{date: views} for one article (days without views are missing from the API's answer)."""
    url = (f"{API}/per-article/{PROJECT}/all-access/user/{quote(article, safe='')}/daily/"
           f"{start:%Y%m%d}00/{end:%Y%m%d}00")
    resp = session.get(url, timeout=60)
    if resp.status_code == 404:
        return {}
    resp.raise_for_status()
    return {pd.Timestamp(i["timestamp"][:8]): int(i["views"]) for i in resp.json().get("items", [])}


# ---------- fetchers ----------


def missing_days(previous, last_day):
    have = set() if previous is None or previous.empty else set(pd.to_datetime(previous["date"]).dt.date)
    days, day = [], last_day
    while day >= FIRST_DAY:
        if day not in have:
            days.append(day)
        day -= timedelta(days=1)
    return days  # newest first


def fetch_top(session, previous, last_day, shared, budget_s=BUDGET_S, clock=time.monotonic):
    days = missing_days(previous, last_day)
    log.info("Wikipedia top lists: %d days to fetch", len(days))
    frames, failed, deadline = [], 0, clock() + budget_s / 2

    def one(day):
        try:
            return fetch_top_day(session, day)
        except Exception as exc:  # noqa: BLE001 - one bad day must not stop the others
            log.warning("top list %s: %s", day, exc)
            return exc

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        step = WORKERS * 10
        for i in range(0, len(days), step):
            if clock() > deadline:
                log.info("Wikipedia top lists: time budget spent, %d days left for later runs", len(days) - i)
                break
            for result in pool.map(one, days[i:i + step]):
                if isinstance(result, Exception):
                    failed += 1
                elif result is not None:
                    frames.append(result)
    if days and not frames and failed:
        raise RuntimeError(f"no Wikipedia top list could be downloaded ({failed} days failed)")
    new = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=TOP.column_names)
    new["is_article"] = is_article(new["article"]).tolist() if len(new) else []
    log.info("Wikipedia top lists: %d days fetched, %d failed", new["date"].nunique() if len(new) else 0, failed)
    full = new if previous is None or previous.empty else pd.concat([previous, new], ignore_index=True)
    shared["top"] = full
    return new


def find_spikes(top, last_day):
    """(article, spike_date, rank) of every spike whose 14 following days are complete."""
    top = top[top["is_article"].astype(bool)]
    days = pd.to_datetime(top["date"])
    present = set(zip(top["article"], days))
    cand = top[(top["rank"] <= SPIKE_RANK) & (days >= pd.Timestamp(FIRST_DAY) + pd.Timedelta(days=QUIET_DAYS))
               & (days + pd.Timedelta(days=AFTER) <= pd.Timestamp(last_day))]
    # Only days whose previous QUIET_DAYS lists all exist, so "absent" really means outside the top 1,000.
    have_days = set(days.dt.normalize())
    rows = []
    for article, day, rank in zip(cand["article"], pd.to_datetime(cand["date"]), cand["rank"]):
        prior = [day - pd.Timedelta(days=k) for k in range(1, QUIET_DAYS + 1)]
        if all(p in have_days for p in prior) and not any((article, p) in present for p in prior):
            rows.append((article, day, int(rank)))
    return pd.DataFrame(rows, columns=["article", "spike_date", "spike_rank"])


def fetch_spike_series(session, previous, last_day, shared, budget_s=BUDGET_S, clock=time.monotonic):
    top = shared.get("top")
    if top is None or top.empty:
        raise RuntimeError("top lists unavailable, spikes cannot be found")
    spikes = find_spikes(top, last_day)
    done = set() if previous is None or previous.empty else set(
        zip(previous["article"], pd.to_datetime(previous["spike_date"])))
    todo = spikes[[(a, d) not in done for a, d in zip(spikes["article"], spikes["spike_date"])]]
    todo = todo.sort_values("spike_date", ascending=False)
    log.info("Wikipedia spikes: %d found, %d to fetch", len(spikes), len(todo))
    frames, failed, deadline = [], 0, clock() + budget_s / 2

    def one(row):
        article, day = row
        start, end = day - pd.Timedelta(days=BEFORE), day + pd.Timedelta(days=AFTER)
        try:
            views = fetch_article_days(session, article, start, end)
        except Exception as exc:  # noqa: BLE001
            log.warning("per-article %s: %s", article, exc)
            return None
        if not views:
            return None
        dates = pd.date_range(start, end, freq="D")
        return pd.DataFrame({"article": article, "spike_date": day, "day_offset": OFFSETS, "date": dates,
                             "views": [views.get(d, 0) for d in dates]})

    jobs = list(zip(todo["article"], todo["spike_date"]))
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        step = WORKERS * 20
        for i in range(0, len(jobs), step):
            if clock() > deadline:
                log.info("Wikipedia spikes: time budget spent, %d spikes left for later runs", len(jobs) - i)
                break
            for result in pool.map(one, jobs[i:i + step]):
                if result is None:
                    failed += 1
                else:
                    frames.append(result)
    log.info("Wikipedia spikes: %d series fetched, %d failed or empty", len(frames), failed)
    if jobs and not frames:
        raise RuntimeError(f"no spike series could be downloaded ({failed} failed)")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=SERIES.column_names)


def make_fetchers(_, snapshot_date):
    last_day = snapshot_date.date() - timedelta(days=1)
    session, shared = make_session(), {}
    return {
        "top_articles": lambda previous: fetch_top(session, previous, last_day, shared),
        "daily_totals": lambda previous: fetch_totals(session, last_day),
        "spike_series": lambda previous: fetch_spike_series(session, previous, last_day, shared),
    }


# ---------- derived ----------


def spike_table(series, top):
    if series is None or series.empty:
        return pd.DataFrame(columns=SPIKES.column_names)
    wide = series.pivot_table(index=["article", "spike_date"], columns="day_offset", values="views", aggfunc="sum")
    wide = wide.reindex(columns=OFFSETS).fillna(0)
    wide.columns = [view_col(o) for o in OFFSETS]
    wide = wide.reset_index()
    ranks = top[["article", "date", "rank"]].rename(columns={"date": "spike_date", "rank": "spike_rank"})
    out = wide.merge(ranks, on=["article", "spike_date"], how="left")
    out["title"] = out["article"].str.replace("_", " ", regex=False)
    out["weekday"] = pd.to_datetime(out["spike_date"]).dt.weekday
    out["baseline_7d"] = out[[view_col(o) for o in range(-BEFORE, 0)]].mean(axis=1).round(1)
    after = out[[view_col(o) for o in range(1, 8)]]
    out["next_7d"] = after.sum(axis=1)
    following = out[[view_col(o) for o in range(1, AFTER + 1)]].to_numpy(dtype=float)
    half = following <= (out["views_d0"].to_numpy(dtype=float)[:, None] / 2)
    first = np.where(half.any(axis=1), half.argmax(axis=1) + 1, np.nan)
    out["half_life_days"] = first
    return out[SPIKES.column_names]


def monthly_top(top, n=50):
    if top is None or top.empty:
        return pd.DataFrame(columns=MONTHLY.column_names)
    t = top[top["is_article"].astype(bool)].copy()
    t["month"] = pd.to_datetime(t["date"]).dt.to_period("M").dt.to_timestamp()
    agg = t.groupby(["month", "article"]).agg(views_in_top_lists=("views", "sum"), days_in_top=("views", "size"),
                                               best_rank=("rank", "min")).reset_index()
    agg = agg.sort_values(["month", "views_in_top_lists"], ascending=[True, False])
    agg["rank"] = agg.groupby("month").cumcount() + 1
    return agg[agg["rank"] <= n][MONTHLY.column_names]


def derive(frames):
    top = frames.get("top_articles")
    return {"attention_spikes": spike_table(frames.get("spike_series"), top if top is not None else pd.DataFrame(
        columns=TOP.column_names)), "monthly_top_articles": monthly_top(top)}


# ---------- description ----------


def coverage_markdown(frames):
    top = frames.get("top_articles") if frames else None
    if top is None or top.empty:
        return "(computed when the dataset is built)"
    series = frames.get("spike_series")
    days = pd.to_datetime(top["date"])
    lines = ["| Table | Rows | First day | Last day |", "|---|---|---|---|",
             f"| Daily top lists | {len(top):,} ({days.nunique():,} days) | {days.min():%Y-%m-%d} | {days.max():%Y-%m-%d} |"]
    if series is not None and not series.empty:
        n = series.groupby(["article", "spike_date"]).ngroups
        sd = pd.to_datetime(series["spike_date"])
        lines.append(f"| Attention spikes with full series | {n:,} | {sd.min():%Y-%m-%d} | {sd.max():%Y-%m-%d} |")
    return "\n".join(lines)


def describe(snapshot_date, tables_written, frames=None):
    return "\n".join([
        "**What Indonesia reads, every day since July 2015**: the 1,000 most-viewed pages of Indonesian "
        "Wikipedia each day, the project's total daily views, and thousands of *attention spikes* (articles "
        "that suddenly jump into the top 100) with their full rise and fall. Updated daily.",
        "",
        "Wikipedia page views are a free, daily signal of public attention: news, deaths of public figures, "
        "elections, disasters, football, TV series, holidays and exams all show up here.",
        "",
        "## Why this dataset",
        "",
        "- **Long and daily**: more than 11 years of daily top lists for Indonesia, kept up to date.",
        "- **Clean**: the main page, search and other non-article pages are flagged (`is_article`).",
        "- **Ready for forecasting**: `attention_spikes` holds each spike's daily views from 7 days before to "
        "14 days after, including the days the article was outside the top list. It is a natural dataset "
        "for demand-shock forecasting: how fast does sudden interest fade? (see the [attention model]"
        "(https://www.kaggle.com/models/danielaijdkx/wikipedia-attention-decay-forecast)).",
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
        "- Views count people (the API's `user` agent): known crawlers and bots are excluded, but some "
        "automated traffic still slips through, so an obscure page with a sudden huge count may be a bot.",
        "- A spike is an article that entered the top 100 on a day after being outside the top 1,000 on "
        "each of the 7 days before. Spikes are added once the 14 days after them have passed.",
        "- `monthly_top_articles` sums views over the days an article was in the daily top 1,000, so its "
        "totals are lower bounds.",
        "- Dates are UTC days (07:00 to 07:00 Western Indonesia Time).",
        "",
        "## Updates",
        "",
        f"Updated daily. Last update: {snapshot_date:%Y-%m-%d} (UTC).",
        "",
        "## Source and license",
        "",
        "Wikimedia Foundation pageviews API (https://wikimedia.org/api/rest_v1/), Indonesian Wikipedia "
        "(id.wikipedia.org). The pageview data is released under CC0; this dataset is CC0 as well.",
    ])


SPEC = DatasetSpec(
    name="idn-wiki",
    slug="indonesian-wikipedia-daily-top-articles",
    title="What Indonesia Reads: Wikipedia Top 1000 Daily",
    subtitle="Indonesian Wikipedia's 1,000 most-read articles every day since 2015",
    license="CC0-1.0",
    keywords=["popular culture", "culture and humanities", "asia", "time series analysis", "data visualization"],
    tables=TABLES,
    sources=(
        "Wikimedia pageviews API (https://wikimedia.org/api/rest_v1/), id.wikipedia.org, CC0. "
        "Built daily by https://github.com/daniel766hi/kaggle-compe"
    ),
    make_fetchers=make_fetchers,
    derive=derive,
    describe=describe,
    cover=ASSETS / "idn-wiki-cover.png",
)
