"""Indonesian politics since the Prabowo administration took office (20 October 2024).

Two public sources, both re-checkable row by row:

- **GDELT** (https://www.gdeltproject.org): machine-coded events from world news coverage, with
  who did what to whom, where, and a link to the source article. Only events located in Indonesia
  are kept, and only "root" events (the main event of a sentence), as GDELT recommends for counts.
  GDELT 1.0 publishes one events file per day; if a day's file is missing, the day is rebuilt from
  GDELT 2.0's 15-minute files. The history since October 2024 is too large for one run, so each run
  refreshes the last days first, then backfills older days until a time budget is spent.
- **Wikidata** (https://www.wikidata.org): who held which cabinet position, from when to when.
  Reshuffles are derived from these dates rather than counted by hand.
"""

import csv
import io
import logging
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..http import USER_AGENT
from ..schema import Column, DatasetSpec, Table, files_markdown
from . import movies

log = logging.getLogger(__name__)

ASSETS = Path(__file__).resolve().parents[2] / "assets"
FIRST_DAY = date(2024, 10, 20)  # inauguration of President Prabowo Subianto
INAUGURATION = pd.Timestamp("2024-10-21")  # the cabinet was sworn in the next day
COUNTRY = "ID"  # FIPS 10-4 code GDELT uses for Indonesia
GDELT1_DAILY = "http://data.gdeltproject.org/events/{day:%Y%m%d}.export.CSV.zip"
GDELT2_15MIN = "http://data.gdeltproject.org/gdeltv2/{stamp}.export.CSV.zip"
CAMEO_EVENTS_URL = "https://www.gdeltproject.org/data/lookups/CAMEO.eventcodes.txt"
CAMEO_TYPES_URL = "https://www.gdeltproject.org/data/lookups/CAMEO.type.txt"
RECENT_DAYS = 3  # always refetched: GDELT keeps adding coverage of the last few days
BUDGET_S = 40 * 60  # time a run may spend backfilling older days
WORKERS = 4

_ACTOR = ["Code", "Name", "CountryCode", "KnownGroupCode", "EthnicCode", "Religion1Code", "Religion2Code",
          "Type1Code", "Type2Code", "Type3Code"]
_EVENT = ["IsRootEvent", "EventCode", "EventBaseCode", "EventRootCode", "QuadClass", "GoldsteinScale",
          "NumMentions", "NumSources", "NumArticles", "AvgTone"]


def _geo(prefix, adm2):
    cols = ["Type", "FullName", "CountryCode", "ADM1Code"] + (["ADM2Code"] if adm2 else []) + ["Lat", "Long", "FeatureID"]
    return [f"{prefix}_{c}" for c in cols]


def _columns(adm2):
    return (["GLOBALEVENTID", "SQLDATE", "MonthYear", "Year", "FractionDate"]
            + [f"Actor1{c}" for c in _ACTOR] + [f"Actor2{c}" for c in _ACTOR] + _EVENT
            + _geo("Actor1Geo", adm2) + _geo("Actor2Geo", adm2) + _geo("ActionGeo", adm2)
            + ["DATEADDED", "SOURCEURL"])


GDELT1_COLUMNS, GDELT2_COLUMNS = _columns(adm2=False), _columns(adm2=True)  # 58 and 61 columns

# CAMEO root codes and GDELT's four broad classes; the full event-code labels are downloaded.
ROOT_LABELS = {
    "01": "Make public statement", "02": "Appeal", "03": "Express intent to cooperate", "04": "Consult",
    "05": "Engage in diplomatic cooperation", "06": "Engage in material cooperation", "07": "Provide aid",
    "08": "Yield", "09": "Investigate", "10": "Demand", "11": "Disapprove", "12": "Reject", "13": "Threaten",
    "14": "Protest", "15": "Exhibit force posture", "16": "Reduce relations", "17": "Coerce", "18": "Assault",
    "19": "Fight", "20": "Use unconventional mass violence",
}
QUAD_LABELS = {1: "verbal cooperation", 2: "material cooperation", 3: "verbal conflict", 4: "material conflict"}

# ---------- tables ----------

EVENTS = Table(
    name="events",
    kind="incremental",
    fmt="parquet",
    description="One row per news event located in Indonesia, as coded by GDELT (root events only).",
    key=("event_id",),
    min_rows=50,
    columns=[
        Column("event_id", "integer", "GDELT GLOBALEVENTID"),
        Column("date", "datetime", "Date of the event as coded by GDELT (SQLDATE)"),
        Column("date_added", "datetime", "Day GDELT first recorded the event"),
        Column("actor1_name", "string", "Who acted (e.g. INDONESIA, PRESIDENT, PROTESTER); empty if not coded"),
        Column("actor1_country", "string", "Actor 1 country (ISO-3, e.g. IDN)"),
        Column("actor1_type", "string", "Actor 1 role, e.g. Government, Police forces, Civilian, Opposition"),
        Column("actor2_name", "string", "Who was acted upon; empty if the event has no target"),
        Column("actor2_country", "string", "Actor 2 country (ISO-3)"),
        Column("actor2_type", "string", "Actor 2 role, e.g. Government, Police forces, Civilian"),
        Column("event_code", "string", "CAMEO event code (e.g. 141 = demonstrate or rally)"),
        Column("event_root_code", "string", "CAMEO root code, 01-20 (14 = protest)"),
        Column("event", "string", "Description of the CAMEO event code"),
        Column("event_root", "string", "Description of the CAMEO root code"),
        Column("quad_class", "string", "verbal/material cooperation or verbal/material conflict"),
        Column("goldstein", "number", "Goldstein scale, -10 (most conflictual) to +10 (most cooperative)"),
        Column("num_mentions", "integer", "Mentions in news on the day GDELT recorded the event"),
        Column("num_sources", "integer", "Distinct news sources reporting the event"),
        Column("num_articles", "integer", "News articles reporting the event"),
        Column("avg_tone", "number", "Average tone of those articles, about -100 to +100 (below 0 = negative)"),
        Column("province", "string", "Province where the event took place (GDELT geocoding); empty if national"),
        Column("location", "string", "Place name as geocoded by GDELT"),
        Column("adm1_code", "string", "GDELT province code (FIPS 10-4, e.g. ID04 = Jakarta)"),
        Column("latitude", "number", "Latitude of the event location"),
        Column("longitude", "number", "Longitude of the event location"),
        Column("source_url", "string", "Link to one news article reporting the event"),
    ],
)

CABINET = Table(
    name="cabinet_positions",
    kind="history",
    description="Who held which position in the Red and White Cabinet, with start and end dates (Wikidata).",
    key=("person_id", "position_id", "start_date"),
    min_rows=20,
    max_shrink=0.1,
    columns=[
        Column("person_id", "string", "Wikidata ID of the person (e.g. Q123)"),
        Column("person", "string", "Name"),
        Column("position_id", "string", "Wikidata ID of the position"),
        Column("position", "string", "Position, e.g. Minister of Finance"),
        Column("start_date", "datetime", "Start of the term in this position"),
        Column("end_date", "datetime", "End of the term; empty while still in office"),
        Column("party", "string", "Political party membership recorded on Wikidata, | separated"),
        Column("replaces", "string", "Previous holder, as recorded on Wikidata"),
        Column("replaced_by", "string", "Next holder, as recorded on Wikidata"),
    ],
)

CHANGES = Table(
    name="cabinet_changes",
    kind="derived",
    description="Cabinet changes after the inauguration, one row per new appointment, derived from cabinet_positions.",
    key=("date", "position_id", "person_id"),
    min_rows=0,
    columns=[
        Column("date", "datetime", "Start date of the new appointment"),
        Column("position_id", "string", "Wikidata ID of the position"),
        Column("position", "string", "Position"),
        Column("person_id", "string", "Wikidata ID of the person appointed"),
        Column("person", "string", "Person appointed"),
        Column("previous_holder", "string", "Who held the position before, from start/end dates; empty if new"),
        Column("appointments_that_day", "integer", "Appointments with the same start date (a reshuffle)"),
    ],
)

DAILY = Table(
    name="daily_national",
    kind="derived",
    description="Per day: number of events, protests and conflict events in Indonesia, and average news tone.",
    key=("date",),
    min_rows=0,
    columns=[
        Column("date", "datetime", "Event date"),
        Column("events", "integer", "Root events located in Indonesia"),
        Column("protests", "integer", "Protest events (CAMEO root 14)"),
        Column("material_conflict", "integer", "Material conflict events (coerce, assault, fight, mass violence)"),
        Column("conflict_share", "number", "Share of events that are verbal or material conflict"),
        Column("articles", "integer", "News articles behind those events"),
        Column("avg_tone", "number", "Average tone, weighted by articles"),
        Column("avg_goldstein", "number", "Average Goldstein score, weighted by articles"),
    ],
)

PROVINCE = Table(
    name="daily_province",
    kind="derived",
    description="Per day and province: events, protests, material conflict and average news tone.",
    key=("date", "province"),
    min_rows=0,
    columns=[
        Column("date", "datetime", "Event date"),
        Column("province", "string", "Province (GDELT geocoding)"),
        Column("events", "integer", "Root events in the province"),
        Column("protests", "integer", "Protest events (CAMEO root 14)"),
        Column("material_conflict", "integer", "Material conflict events"),
        Column("articles", "integer", "News articles behind those events"),
        Column("avg_tone", "number", "Average tone, weighted by articles"),
    ],
)

TABLES = [EVENTS, CABINET, CHANGES, DAILY, PROVINCE]

# ---------- GDELT ----------


def make_session():
    session = requests.Session()
    retry = Retry(total=5, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=("GET",))
    adapter = HTTPAdapter(max_retries=retry, pool_maxsize=WORKERS * 2)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers["User-Agent"] = USER_AGENT
    return session


def lookup(session, url):
    """A GDELT lookup file (code<TAB>label) as a dict; empty if it can't be downloaded."""
    try:
        resp = session.get(url, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.warning("Could not download %s (%s); using codes without labels", url, exc)
        return {}
    rows = [line.split("\t") for line in resp.text.splitlines()[1:] if "\t" in line]
    return {code.strip(): label.strip() for code, label, *_ in rows}


def read_export(content):
    """Rows of one GDELT export zip that are root events located in Indonesia."""
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        raw = z.read(z.namelist()[0])
    # Cheap pre-filter on the raw bytes before parsing: keep lines mentioning the country code.
    lines = [line for line in raw.split(b"\n") if b"\tID\t" in line]
    if not lines:
        return pd.DataFrame(columns=GDELT1_COLUMNS)
    text = b"\n".join(lines).decode("utf-8", errors="replace")
    df = pd.read_csv(io.StringIO(text), sep="\t", header=None, dtype=str, quoting=csv.QUOTE_NONE,
                     on_bad_lines="skip", keep_default_na=False)
    if df.shape[1] == len(GDELT2_COLUMNS):
        df.columns = GDELT2_COLUMNS
    elif df.shape[1] == len(GDELT1_COLUMNS):
        df.columns = GDELT1_COLUMNS
    else:
        raise ValueError(f"unexpected GDELT export with {df.shape[1]} columns")
    return df[(df["ActionGeo_CountryCode"] == COUNTRY) & (df["IsRootEvent"] == "1")]


def _get(session, url):
    resp = session.get(url, timeout=120)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.content


def fetch_day(session, day):
    """All Indonesian root events GDELT recorded on one day (by DATEADDED)."""
    content = _get(session, GDELT1_DAILY.format(day=day))
    if content is not None:
        return read_export(content)
    # No GDELT 1.0 file for this day: rebuild it from the 96 GDELT 2.0 quarter-hour files.
    parts, missing = [], 0
    for minutes in range(0, 24 * 60, 15):
        stamp = f"{day:%Y%m%d}{minutes // 60:02d}{minutes % 60:02d}00"
        content = _get(session, GDELT2_15MIN.format(stamp=stamp))
        if content is None:
            missing += 1
            continue
        parts.append(read_export(content))
    if missing > 8:  # a few gaps are normal in GDELT 2.0; many mean the day isn't published yet
        raise FileNotFoundError(f"GDELT has no complete data for {day} ({missing} of 96 files missing)")
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=GDELT2_COLUMNS)


def province_of(full_name, geo_type):
    """GDELT location names look like 'City, Province, Indonesia' or 'Province, Indonesia'.
    Geo type 1 is a whole country, so it has no province."""
    if not isinstance(full_name, str) or geo_type == "1":
        return None
    parts = [p.strip() for p in full_name.split(",")]
    return parts[-2] if len(parts) >= 2 else None


def tidy_events(raw, event_labels, type_labels):
    """Raw GDELT columns -> the published events table."""
    def actor_type(codes):
        return codes.map(lambda c: type_labels.get(c, c.title()) if c else None)

    root = raw["EventRootCode"].str.zfill(2)
    quad = pd.to_numeric(raw["QuadClass"], errors="coerce")
    added = raw["DATEADDED"].str[:8]
    return pd.DataFrame({
        "event_id": raw["GLOBALEVENTID"],
        "date": pd.to_datetime(raw["SQLDATE"], format="%Y%m%d", errors="coerce"),
        "date_added": pd.to_datetime(added, format="%Y%m%d", errors="coerce"),
        "actor1_name": raw["Actor1Name"].replace("", None),
        "actor1_country": raw["Actor1CountryCode"].replace("", None),
        "actor1_type": actor_type(raw["Actor1Type1Code"]),
        "actor2_name": raw["Actor2Name"].replace("", None),
        "actor2_country": raw["Actor2CountryCode"].replace("", None),
        "actor2_type": actor_type(raw["Actor2Type1Code"]),
        "event_code": raw["EventCode"],
        "event_root_code": root,
        "event": raw["EventCode"].map(event_labels),
        "event_root": root.map(ROOT_LABELS),
        "quad_class": quad.map(QUAD_LABELS),
        "goldstein": raw["GoldsteinScale"],
        "num_mentions": raw["NumMentions"],
        "num_sources": raw["NumSources"],
        "num_articles": raw["NumArticles"],
        "avg_tone": raw["AvgTone"],
        "province": [province_of(n, t) for n, t in zip(raw["ActionGeo_FullName"], raw["ActionGeo_Type"])],
        "location": raw["ActionGeo_FullName"].replace("", None),
        "adm1_code": raw["ActionGeo_ADM1Code"].replace("", None),
        "latitude": raw["ActionGeo_Lat"],
        "longitude": raw["ActionGeo_Long"],
        "source_url": raw["SOURCEURL"].replace("", None),
    })


def plan_days(previous, last_day, first_day=FIRST_DAY, recent_days=RECENT_DAYS):
    """Days to fetch, in order: the recent window first, then missing days from newest to oldest."""
    have = set()
    if previous is not None and not previous.empty:
        have = set(pd.to_datetime(previous["date_added"]).dt.date.dropna())
    recent = [last_day - timedelta(days=i) for i in range(recent_days) if last_day - timedelta(days=i) >= first_day]
    older = []
    day = last_day - timedelta(days=recent_days)
    while day >= first_day:
        if day not in have:
            older.append(day)
        day -= timedelta(days=1)
    return recent, older


def fetch_events(session, previous, last_day, budget_s=BUDGET_S, clock=time.monotonic):
    event_labels, type_labels = lookup(session, CAMEO_EVENTS_URL), lookup(session, CAMEO_TYPES_URL)
    recent, older = plan_days(previous, last_day)
    log.info("GDELT: %d recent days to refresh, %d older days missing", len(recent), len(older))
    frames, failed = [], []

    def one(day):
        try:
            return day, fetch_day(session, day)
        except Exception as exc:  # noqa: BLE001 - one bad day must not stop the others
            return day, exc

    def collect(results):
        for day, result in results:
            if isinstance(result, Exception):
                failed.append(day)
                log.warning("GDELT %s: %s", day, result)
            else:
                frames.append(result)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        collect(pool.map(one, recent))
        deadline = clock() + budget_s
        for start in range(0, len(older), WORKERS * 4):
            if clock() > deadline:
                log.info("GDELT: time budget spent; %d older days left for the next runs", len(older) - start)
                break
            collect(pool.map(one, older[start:start + WORKERS * 4]))
            done = min(start + WORKERS * 4, len(older))
            if done % 40 == 0 or done == len(older):
                log.info("GDELT: backfilled %d / %d older days", done, len(older))
    if not frames:
        raise RuntimeError(f"no GDELT data could be downloaded ({len(failed)} days failed)")
    raw = pd.concat(frames, ignore_index=True)
    events = tidy_events(raw, event_labels, type_labels)
    events = events[events["date"] >= pd.Timestamp(FIRST_DAY)]
    log.info("GDELT: %d events from %d files (%d days failed)", len(events), len(frames), len(failed))
    return events

# ---------- Wikidata: cabinet ----------


CABINET_QUERY = """
SELECT ?person ?personLabel ?position ?positionLabel ?start ?end ?replaces ?replacesLabel
       ?replacedBy ?replacedByLabel WHERE {
  VALUES ?cabinet { %s }
  ?person p:P39 ?st .
  ?st ps:P39 ?position ; pq:P5054 ?cabinet .
  OPTIONAL { ?st pq:P580 ?start }
  OPTIONAL { ?st pq:P582 ?end }
  OPTIONAL { ?st pq:P1365 ?replaces }
  OPTIONAL { ?st pq:P1366 ?replacedBy }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,id". }
}
"""

PARTY_QUERY = """
SELECT ?person ?partyLabel WHERE {
  VALUES ?person { %s }
  ?person wdt:P102 ?party .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,id". }
}
"""

CABINET_LABELS = ['"Red and White Cabinet"@en', '"Kabinet Merah Putih"@id']


def find_cabinet(session):
    union = " UNION ".join(f"{{ ?c rdfs:label {label} }}" for label in CABINET_LABELS)
    rows = movies.sparql(session, f"SELECT DISTINCT ?c WHERE {{ {union} }}")
    ids = sorted({movies.qid(r["c"]) for r in rows})
    if not ids:
        raise RuntimeError("Wikidata has no item labelled 'Red and White Cabinet'")
    log.info("Wikidata cabinet item(s): %s", ", ".join(ids))
    return ids


def cabinet_frame(rows, party_rows):
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=CABINET.column_names)
    for col in ["start", "end", "replacesLabel", "replacedByLabel"]:
        if col not in df:
            df[col] = None
    parties = (pd.DataFrame(party_rows, columns=["person", "partyLabel"]).dropna()
               .groupby("person")["partyLabel"].agg(lambda s: "|".join(sorted(set(s)))))
    out = pd.DataFrame({
        "person_id": df["person"].map(movies.qid),
        "person": df["personLabel"],
        "position_id": df["position"].map(movies.qid),
        "position": df["positionLabel"],
        "start_date": pd.to_datetime(df["start"].astype("string").str[:10], errors="coerce"),
        "end_date": pd.to_datetime(df["end"].astype("string").str[:10], errors="coerce"),
        "party": df["person"].map(parties),
        "replaces": df["replacesLabel"],
        "replaced_by": df["replacedByLabel"],
    })
    # Terms without a start date are taken to start with the cabinet.
    out["start_date"] = out["start_date"].fillna(INAUGURATION)
    return out


def fetch_cabinet(session):
    ids = find_cabinet(session)
    rows = movies.sparql(session, CABINET_QUERY % " ".join(f"wd:{i}" for i in ids))
    people = sorted({movies.qid(r["person"]) for r in rows})
    party_rows = []
    for i in range(0, len(people), 200):
        party_rows += movies.sparql(session, PARTY_QUERY % " ".join(f"wd:{p}" for p in people[i:i + 200]))
    df = cabinet_frame(rows, party_rows)
    log.info("Wikidata: %d cabinet terms, %d people, %d positions", len(df), df["person_id"].nunique(),
             df["position_id"].nunique())
    return df

# ---------- derived ----------


def cabinet_changes(cabinet):
    if cabinet is None or cabinet.empty:
        return pd.DataFrame(columns=CHANGES.column_names)
    terms = cabinet.sort_values("start_date")
    new = terms[terms["start_date"] > INAUGURATION].copy()
    previous = []
    for row in new.itertuples():
        before = terms[(terms["position_id"] == row.position_id) & (terms["start_date"] < row.start_date)
                       & (terms["person_id"] != row.person_id)]
        previous.append(before["person"].iloc[-1] if len(before) else None)
    new["previous_holder"] = previous
    new["appointments_that_day"] = new.groupby("start_date")["person_id"].transform("size")
    return new.rename(columns={"start_date": "date"})[CHANGES.column_names]


def _weighted(df, value, weight="num_articles"):
    w = df[weight].fillna(0).astype(float)
    v = df[value].astype(float)
    return (v * w).sum() / w.sum() if w.sum() else float("nan")


def _summary(group):
    return pd.Series({
        "events": len(group),
        "protests": int((group["event_root_code"] == "14").sum()),
        "material_conflict": int((group["quad_class"] == "material conflict").sum()),
        "conflict_share": group["quad_class"].isin(["verbal conflict", "material conflict"]).mean(),
        "articles": int(group["num_articles"].fillna(0).sum()),
        "avg_tone": _weighted(group, "avg_tone"),
        "avg_goldstein": _weighted(group, "goldstein"),
    })


def daily_tables(events):
    if events is None or events.empty:
        return pd.DataFrame(columns=DAILY.column_names), pd.DataFrame(columns=PROVINCE.column_names)
    national = events.groupby("date").apply(_summary, include_groups=False).reset_index()
    by_province = (events.dropna(subset=["province"]).groupby(["date", "province"])
                   .apply(_summary, include_groups=False).reset_index())
    return national, by_province[PROVINCE.column_names]


def derive(frames):
    national, by_province = daily_tables(frames.get("events"))
    return {"cabinet_changes": cabinet_changes(frames.get("cabinet_positions")),
            "daily_national": national, "daily_province": by_province}


def make_fetchers(_, snapshot_date):
    last_day = snapshot_date.date() - timedelta(days=1)
    return {
        "events": lambda previous: fetch_events(make_session(), previous, last_day),
        "cabinet_positions": lambda previous: fetch_cabinet(movies.make_session()),
    }

# ---------- description ----------


def coverage_markdown(frames):
    events = frames.get("events") if frames else None
    if events is None or events.empty:
        return "(computed when the dataset is built)"
    days = events["date_added"].dt.date.nunique()
    expected = (events["date_added"].max().date() - FIRST_DAY).days + 1
    return (f"{len(events):,} events from {events['date'].min():%Y-%m-%d} to {events['date'].max():%Y-%m-%d}; "
            f"GDELT files for {days} of {expected} days are included so far. Missing days are filled in "
            "automatically over the next runs.")


def describe(snapshot_date, tables_written, frames=None):
    return "\n".join([
        "What happened in Indonesian politics since President Prabowo Subianto took office on 20 October 2024: "
        "**protests, government actions, statements, clashes and cabinet changes**, updated every day "
        "from two public sources that anyone can check.",
        "",
        "## Why this dataset",
        "",
        "- **Every row can be verified.** Events link to the news article they come from; cabinet terms come "
        "from Wikidata, with Wikidata IDs.",
        "- **Updated daily** by an automated pipeline, so it keeps covering new events.",
        "- **Ready for analysis.** Daily national and per-province summaries (events, protests, conflict, news "
        "tone) are included next to the event-level data.",
        "",
        "## Files",
        "",
        files_markdown(tables_written),
        "",
        "## Coverage",
        "",
        coverage_markdown(frames),
        "",
        "## How to read the event data",
        "",
        "GDELT reads news coverage worldwide and codes each reported action with the CAMEO scheme: who did what "
        "(`event`, e.g. *Demonstrate or rally*) to whom, where. `quad_class` groups events into verbal or "
        "material cooperation and conflict. `goldstein` rates an event's typical effect on stability "
        "(-10 to +10), and `avg_tone` is how negative or positive the reporting was.",
        "",
        "Limits worth knowing:",
        "",
        "- It is **machine-coded**: some events are misclassified or geocoded to the wrong place, and one real "
        "event can appear several times when it is reported differently. Counts are best used as **trends** "
        "(compare days, months and provinces), not as exact tallies. Opening a few `source_url` links is a "
        "good habit.",
        "- It measures **news coverage**. Events that the media covers heavily (for example in Jakarta) are "
        "over-represented compared with remote regions.",
        "- Only *root* events located in Indonesia are kept (`ActionGeo` = Indonesia).",
        "",
        "## Cabinet data",
        "",
        "`cabinet_positions` lists every term in the Red and White Cabinet recorded on Wikidata (positions held "
        "with the cabinet qualifier), with start and end dates. `cabinet_changes` lists appointments after the "
        "inauguration and the previous holder, so reshuffles show up as days with several appointments. "
        "Wikidata is edited by volunteers: a missing end date can mean the term is ongoing or not yet recorded.",
        "",
        "## Updates",
        "",
        f"Updated daily from GDELT and Wikidata. Last update: {snapshot_date:%Y-%m-%d} (UTC).",
        "",
        "## Sources and terms",
        "",
        "- Events: [The GDELT Project](https://www.gdeltproject.org), free for any use with citation. "
        "Please cite GDELT when using the event data.",
        "- Cabinet: [Wikidata](https://www.wikidata.org), CC0.",
        "",
        "Earlier versions of this dataset (up to October 2026) were a small hand-collected set of notes. "
        "They were replaced by this verifiable, automatically updated version.",
    ])


SPEC = DatasetSpec(
    name="idn-politics",
    slug="indonesian-political-moves-database-2024-2026",
    title="Indonesia Politics Tracker: Events & Cabinet",
    subtitle="Daily GDELT events, protests and cabinet changes in Indonesia since Oct 2024",
    license="CC0-1.0",
    keywords=["politics", "government", "asia", "time series analysis", "tabular"],
    tables=TABLES,
    sources=(
        "The GDELT Project (https://www.gdeltproject.org), daily events export; "
        "Wikidata (https://www.wikidata.org), CC0, via https://query.wikidata.org. "
        "Built daily by https://github.com/daniel766hi/kaggle-compe"
    ),
    make_fetchers=make_fetchers,
    derive=derive,
    describe=describe,
    cover=ASSETS / "idn-politics-cover.png",
)
