"""Movie metadata from Wikidata (CC0): genres, crew, cast, color, aspect ratio, money and awards.

Only notable feature films are included: those with Wikipedia articles (sitelinks) in at least
MIN_SITELINKS languages. Obscure entries have almost no metadata, so they would mostly add
empty rows.

Data is pulled through the Wikidata SPARQL endpoint: first the list of film IDs, then the details
in batches (VALUES blocks), which keeps every query far below the endpoint's 60-second limit.
"""

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..http import USER_AGENT
from ..schema import Column, DatasetSpec, Table, files_markdown

log = logging.getLogger(__name__)

ASSETS = Path(__file__).resolve().parents[2] / "assets"
SPARQL_URL = "https://query.wikidata.org/sparql"
MIN_SITELINKS = 10
BATCH = 200
PAUSE_S = 1.0  # between queries of one worker; Wikidata asks bots to be gentle
WORKERS = 4

WD = "http://www.wikidata.org/entity/"
USD = "Q4917"
MINUTE, HOUR, SECOND = "Q7727", "Q25235", "Q11574"
WORLDWIDE = "Q13780930"
ROTTEN_TOMATOES, METACRITIC = "Q105584", "Q150248"
TOMATOMETER = "Q108403393"  # "Tomatometer score" (determination method)

# Item-valued properties: (column/role name, property id, table they go to)
RELATIONS = [
    ("genre", "P136", "genres"),
    ("color", "P462", "attributes"),
    ("aspect_ratio", "P2061", "attributes"),
    ("country", "P495", "attributes"),
    ("original_language", "P364", "attributes"),
    ("mpa_rating", "P1657", "attributes"),
    ("distribution_format", "P437", "attributes"),
    ("series", "P179", "attributes"),
    ("based_on", "P144", "attributes"),
    ("production_company", "P272", "attributes"),
    ("distributor", "P750", "attributes"),
    ("director", "P57", "crew"),
    ("screenwriter", "P58", "crew"),
    ("producer", "P162", "crew"),
    ("cinematographer", "P344", "crew"),
    ("composer", "P86", "crew"),
    ("editor", "P1040", "crew"),
    ("production_designer", "P2554", "crew"),
    ("costume_designer", "P2515", "crew"),
    ("cast", "P161", "cast"),
    ("award_won", "P166", "awards"),
    ("award_nominated", "P1411", "awards"),
]

# ---------- tables ----------

FILM_ID = Column("film_id", "string", "Wikidata ID of the film (e.g. Q25188 = Inception); join key for all files")

TABLES = [
    Table(
        name="movies",
        kind="history",
        description="One row per film: title, release, runtime, color, aspect ratio, money, ratings and summary columns.",
        columns=[
            FILM_ID,
            Column("title", "string", "English title (Wikidata English label)"),
            Column("original_title", "string", "Title in the original language, when recorded"),
            Column("release_date", "datetime", "Earliest recorded publication (release) date"),
            Column("release_year", "integer", "Year of release_date"),
            Column("runtime_min", "number", "Duration in minutes"),
            Column("color", "string", "Color process: e.g. 'color', 'black-and-white' (several separated by '|')"),
            Column("aspect_ratio", "string", "Aspect ratio of the image, e.g. '2.39:1' (several separated by '|')"),
            Column("genres", "string", "All genres, separated by '|' (one row per genre in movie_genres.csv)"),
            Column("directors", "string", "Director name(s), separated by '|'"),
            Column("countries", "string", "Country/countries of origin, separated by '|'"),
            Column("original_languages", "string", "Original language(s), separated by '|'"),
            Column("mpa_rating", "string", "US Motion Picture Association rating, e.g. 'R'"),
            Column("distribution_formats", "string", "Release/distribution formats, e.g. '35 mm film', 'video on demand'"),
            Column("production_companies", "string", "Production companies, separated by '|'"),
            Column("distributors", "string", "Distributors, separated by '|'"),
            Column("series", "string", "Film series or franchise the film belongs to"),
            Column("based_on", "string", "Work(s) the film is based on (novel, play, ...), separated by '|'"),
            Column("budget_usd", "number", "Production budget in US dollars (only budgets recorded in USD)"),
            Column("box_office_usd", "number", "Box office gross in US dollars, worldwide where recorded (only USD values)"),
            Column("rotten_tomatoes_pct", "number", "Rotten Tomatoes Tomatometer score, % of positive critic reviews"),
            Column("metacritic_score", "number", "Metacritic critic score, 0-100"),
            Column("oscar_wins", "integer", "Number of Academy Awards won"),
            Column("oscar_nominations", "integer", "Number of Academy Award nominations (including wins where recorded)"),
            Column("n_cast", "integer", "Number of cast members recorded"),
            Column("wikipedia_languages", "integer", "Number of Wikipedia language editions with an article (popularity proxy)"),
            Column("imdb_id", "string", "IMDb identifier (tt...), to join with other datasets"),
            Column("tmdb_id", "string", "TMDB movie identifier, to join with other datasets"),
        ],
        min_rows=5000,
        key=("film_id",),
        max_shrink=0.03,
    ),
    Table(
        name="movie_genres",
        kind="history",
        description="One row per film and genre.",
        columns=[FILM_ID, Column("genre_id", "string", "Wikidata ID of the genre"),
                 Column("genre", "string", "Genre name, e.g. 'drama film', 'science fiction film'")],
        min_rows=5000,
        key=("film_id", "genre_id"),
        max_shrink=0.03,
    ),
    Table(
        name="movie_crew",
        kind="history",
        description="One row per film and crew credit: directors, writers, producers, cinematographers, composers, editors, designers.",
        columns=[FILM_ID,
                 Column("role", "string", "director, screenwriter, producer, cinematographer, composer, editor, "
                                          "production_designer or costume_designer"),
                 Column("person_id", "string", "Wikidata ID of the person (stable across films)"),
                 Column("person", "string", "Person's name")],
        min_rows=10000,
        key=("film_id", "role", "person_id"),
        max_shrink=0.03,
    ),
    Table(
        name="movie_cast",
        kind="history",
        description="One row per film and cast member, with billing order where recorded.",
        columns=[FILM_ID,
                 Column("person_id", "string", "Wikidata ID of the actor"),
                 Column("person", "string", "Actor's name"),
                 Column("cast_order", "integer", "Billing order (1 = first billed); rarely recorded in Wikidata, "
                                                  "mostly empty")],
        min_rows=10000,
        key=("film_id", "person_id"),
        max_shrink=0.03,
    ),
    Table(
        name="movie_awards",
        kind="history",
        description="One row per award won or nominated for (Oscars, Golden Globes, BAFTA, festivals, ...).",
        columns=[FILM_ID,
                 Column("outcome", "string", "'won' or 'nominated'"),
                 Column("award_id", "string", "Wikidata ID of the award category"),
                 Column("award", "string", "Award name, e.g. 'Academy Award for Best Picture'"),
                 Column("year", "integer", "Year of the award, when recorded")],
        min_rows=1000,
        key=("film_id", "outcome", "award_id"),
        max_shrink=0.03,
    ),
]

# ---------- SPARQL ----------


def make_session():
    session = requests.Session()
    retry = Retry(total=6, backoff_factor=3, status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=("GET", "POST"), respect_retry_after_header=True)
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers["User-Agent"] = USER_AGENT
    session.headers["Accept"] = "application/sparql-results+json"
    return session


def sparql(session, query):
    """Run a query and return rows as dicts of plain strings."""
    resp = session.post(SPARQL_URL, data={"query": query}, timeout=120)
    resp.raise_for_status()
    time.sleep(PAUSE_S)
    return [{k: v["value"] for k, v in b.items()} for b in resp.json()["results"]["bindings"]]


def qid(uri):
    return uri.rsplit("/", 1)[-1] if isinstance(uri, str) and uri else None


def film_list(session, min_sitelinks=MIN_SITELINKS):
    rows = sparql(session, f"""
        SELECT ?film ?links (MIN(?date) AS ?first) WHERE {{
          ?film wdt:P31 wd:Q11424 ; wikibase:sitelinks ?links .
          FILTER(?links >= {min_sitelinks})
          OPTIONAL {{ ?film wdt:P577 ?date }}
        }} GROUP BY ?film ?links""")
    return pd.DataFrame({
        "film_id": [qid(r["film"]) for r in rows],
        "wikipedia_languages": [int(r["links"]) for r in rows],
        "release_date": [r.get("first", "")[:10] or None for r in rows],
    })


def _values(ids):
    return " ".join(f"wd:{i}" for i in ids)


def basics(session, ids):
    return sparql(session, f"""
        SELECT ?film (SAMPLE(?label) AS ?title) (SAMPLE(?orig) AS ?original_title)
               (SAMPLE(?imdb) AS ?imdb_id) (SAMPLE(?tmdb) AS ?tmdb_id) WHERE {{
          VALUES ?film {{ {_values(ids)} }}
          OPTIONAL {{ ?film rdfs:label ?label FILTER(LANG(?label) = "en") }}
          OPTIONAL {{ ?film wdt:P1476 ?orig }}
          OPTIONAL {{ ?film wdt:P345 ?imdb }}
          OPTIONAL {{ ?film wdt:P4947 ?tmdb }}
        }} GROUP BY ?film""")


def relations(session, ids):
    props = " ".join(f'("{name}" p:{pid} ps:{pid})' for name, pid, _ in RELATIONS)
    return sparql(session, f"""
        SELECT ?film ?rel ?value ?valueLabel ?when ?ord WHERE {{
          VALUES ?film {{ {_values(ids)} }}
          VALUES (?rel ?p ?ps) {{ {props} }}
          ?film ?p ?st . ?st ?ps ?value ; wikibase:rank ?rank .
          FILTER(?rank != wikibase:DeprecatedRank)
          FILTER(ISIRI(?value))
          OPTIONAL {{ ?value rdfs:label ?valueLabel FILTER(LANG(?valueLabel) = "en") }}
          OPTIONAL {{ ?st pq:P585 ?when }}
          OPTIONAL {{ ?st pq:P1545 ?ord }}
        }}""")


def quantities(session, ids):
    return sparql(session, f"""
        SELECT ?film ?prop ?amount ?unit ?place WHERE {{
          VALUES ?film {{ {_values(ids)} }}
          VALUES (?prop ?p ?psv) {{ ("runtime" p:P2047 psv:P2047) ("budget" p:P2130 psv:P2130)
                                   ("box_office" p:P2142 psv:P2142) }}
          ?film ?p ?st . ?st ?psv ?node ; wikibase:rank ?rank .
          FILTER(?rank != wikibase:DeprecatedRank)
          ?node wikibase:quantityAmount ?amount ; wikibase:quantityUnit ?unit .
          OPTIONAL {{ ?st pq:P3005 ?place }}
        }}""")


def reviews(session, ids):
    return sparql(session, f"""
        SELECT ?film ?score ?by ?method WHERE {{
          VALUES ?film {{ {_values(ids)} }}
          ?film p:P444 ?st . ?st ps:P444 ?score ; pq:P447 ?by .
          VALUES ?by {{ wd:{ROTTEN_TOMATOES} wd:{METACRITIC} }}
          OPTIONAL {{ ?st pq:P459 ?method }}
        }}""")


# ---------- parsing ----------

def parse_runtime(amount, unit):
    value = float(amount)
    return {MINUTE: value, HOUR: value * 60, SECOND: value / 60}.get(unit)


def pick_money(rows):
    """Largest USD value, preferring worldwide figures when a place qualifier is given."""
    usd = [r for r in rows if r["unit"] == USD]
    if not usd:
        return None
    worldwide = [r for r in usd if r["place"] in (None, WORLDWIDE)]
    return max(float(r["amount"]) for r in (worldwide or usd))


def parse_score(text):
    """'93%' -> 93, '74/100' -> 74, '8.1/10' -> 81. Returns None if unparseable."""
    m = re.match(r"^\s*([\d.]+)\s*(%|/\s*([\d.]+))?\s*$", text or "")
    if not m:
        return None
    value = float(m.group(1))
    if m.group(3):
        value = value / float(m.group(3)) * 100
    return value if 0 <= value <= 100 else None


def build_tables(films, basic_rows, relation_rows, quantity_rows, review_rows):
    """Turn raw SPARQL rows into the dataset tables (pure function, tested offline)."""
    rel = pd.DataFrame(relation_rows, columns=["film", "rel", "value", "valueLabel", "when", "ord"])
    rel["film_id"], rel["value_id"] = rel["film"].map(qid), rel["value"].map(qid)
    rel["name"] = rel["valueLabel"].fillna(rel["value_id"])
    kind = {name: table for name, _, table in RELATIONS}

    def joined(name):
        sub = rel[rel["rel"] == name].drop_duplicates(["film_id", "value_id"])
        return sub.groupby("film_id")["name"].agg(lambda s: "|".join(sorted(s)))

    genres = rel[rel["rel"] == "genre"][["film_id", "value_id", "name"]].rename(
        columns={"value_id": "genre_id", "name": "genre"})
    crew_rel = rel[rel["rel"].map(kind) == "crew"]
    crew = crew_rel[["film_id", "rel", "value_id", "name"]].rename(
        columns={"rel": "role", "value_id": "person_id", "name": "person"})
    cast_rel = rel[rel["rel"] == "cast"]
    cast = cast_rel.assign(cast_order=pd.to_numeric(cast_rel["ord"], errors="coerce"))[
        ["film_id", "value_id", "name", "cast_order"]].rename(columns={"value_id": "person_id", "name": "person"})
    cast = cast.sort_values("cast_order").drop_duplicates(["film_id", "person_id"])
    aw = rel[rel["rel"].isin(["award_won", "award_nominated"])]
    awards = pd.DataFrame({
        "film_id": aw["film_id"],
        "outcome": aw["rel"].map({"award_won": "won", "award_nominated": "nominated"}),
        "award_id": aw["value_id"], "award": aw["name"],
        "year": pd.to_numeric(aw["when"].astype("string").str[:4], errors="coerce"),
    })

    movies = films.copy()
    basic = pd.DataFrame(basic_rows, columns=["film", "title", "original_title", "imdb_id", "tmdb_id"])
    basic["film_id"] = basic["film"].map(qid)
    movies = movies.merge(basic.drop(columns="film"), on="film_id", how="left")
    for col, name in [("color", "color"), ("aspect_ratio", "aspect_ratio"), ("genres", "genre"),
                      ("directors", "director"), ("countries", "country"), ("original_languages", "original_language"),
                      ("mpa_rating", "mpa_rating"), ("distribution_formats", "distribution_format"),
                      ("production_companies", "production_company"), ("distributors", "distributor"),
                      ("series", "series"), ("based_on", "based_on")]:
        movies[col] = movies["film_id"].map(joined(name))

    q = pd.DataFrame(quantity_rows, columns=["film", "prop", "amount", "unit", "place"])
    q["film_id"], q["unit"], q["place"] = q["film"].map(qid), q["unit"].map(qid), q["place"].map(qid)
    q = q.where(q.notna(), None)
    runtime = q[q["prop"] == "runtime"].assign(m=lambda d: [parse_runtime(a, u) for a, u in zip(d["amount"], d["unit"])])
    movies["runtime_min"] = movies["film_id"].map(runtime.dropna(subset=["m"]).groupby("film_id")["m"].max())
    for prop, col in [("budget", "budget_usd"), ("box_office", "box_office_usd")]:
        sub = q[q["prop"] == prop]
        money = {f: pick_money(g.to_dict("records")) for f, g in sub.groupby("film_id")}
        movies[col] = movies["film_id"].map(money)

    r = pd.DataFrame(review_rows, columns=["film", "score", "by", "method"])
    r["film_id"], r["by"], r["method"] = r["film"].map(qid), r["by"].map(qid), r["method"].map(qid)
    r["value"] = r["score"].map(parse_score)
    rt = r[(r["by"] == ROTTEN_TOMATOES) & (r["method"].isna() | (r["method"] == TOMATOMETER))
           & r["score"].fillna("").str.contains("%")]
    mc = r[(r["by"] == METACRITIC) & r["score"].fillna("").str.contains("/100")]
    movies["rotten_tomatoes_pct"] = movies["film_id"].map(rt.groupby("film_id")["value"].max())
    movies["metacritic_score"] = movies["film_id"].map(mc.groupby("film_id")["value"].max())

    oscar = awards["award"].fillna("").str.startswith("Academy Award for")
    movies["oscar_wins"] = movies["film_id"].map(awards[oscar & (awards["outcome"] == "won")]
                                                 .drop_duplicates(["film_id", "award_id"]).groupby("film_id").size()).fillna(0)
    movies["oscar_nominations"] = movies["film_id"].map(awards[oscar].drop_duplicates(["film_id", "award_id"])
                                                        .groupby("film_id").size()).fillna(0)
    movies["n_cast"] = movies["film_id"].map(cast.groupby("film_id").size()).fillna(0)
    movies["release_date"] = pd.to_datetime(movies["release_date"], errors="coerce")
    movies["release_year"] = movies["release_date"].dt.year
    movies["title"] = movies["title"].fillna(movies["original_title"])
    return {"movies": movies, "movie_genres": genres, "movie_crew": crew, "movie_cast": cast, "movie_awards": awards}


def fetch_batch(batch):
    session = make_session()  # one session per worker thread
    return basics(session, batch), relations(session, batch), quantities(session, batch), reviews(session, batch)


def fetch_all(session):
    films = film_list(session)
    log.info("%d films with >= %d Wikipedia languages", len(films), MIN_SITELINKS)
    ids = films["film_id"].tolist()
    batches = [ids[i:i + BATCH] for i in range(0, len(ids), BATCH)]
    parts = {"basic": [], "rel": [], "qty": [], "rev": []}
    # Wikidata allows up to 5 parallel queries per client; 4 keeps a margin.
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for done, (b, r, q, v) in enumerate(pool.map(fetch_batch, batches), start=1):
            parts["basic"] += b
            parts["rel"] += r
            parts["qty"] += q
            parts["rev"] += v
            if done % 20 == 0 or done == len(batches):
                log.info("details: %d / %d batches", done, len(batches))
    return build_tables(films, parts["basic"], parts["rel"], parts["qty"], parts["rev"])


def make_fetchers(_, snapshot_date):
    cache = {}

    def table(name):
        def fetch(previous):
            if "all" not in cache:
                cache["all"] = fetch_all(make_session())
            return cache["all"][name]
        return fetch

    return {t.name: table(t.name) for t in TABLES}


def completeness_markdown(movies):
    if movies is None or movies.empty:
        return "(computed when the dataset is built)"
    filled = (movies.notna().mean() * 100).drop(["film_id", "wikipedia_languages", "oscar_wins",
                                                 "oscar_nominations", "n_cast"], errors="ignore")
    lines = ["| Column | Filled |", "|---|---|"]
    lines += [f"| `{col}` | {pct:.0f}% |" for col, pct in filled.sort_values(ascending=False).items()]
    return "\n".join(lines)


def describe(snapshot_date, tables_written, frames=None):
    return "\n".join([
        "Metadata for **notable feature films**, from the early days of cinema to this year's releases: "
        "genres, directors, writers, cast, cinematographers, composers, color vs black-and-white, aspect "
        "ratio, runtime, country, language, budget, box office, critic scores and awards.",
        "",
        "## Why this dataset",
        "",
        "- **Free to use (CC0).** Built from Wikidata, which is public domain, so unlike datasets copied from "
        "IMDb or TMDB, you can use it for anything.",
        "- **Relational.** One clean film table plus long tables for genres, crew, cast and awards, joined by "
        "`film_id`. Ideal for SQL practice, network analysis (who works with whom) and recommender systems.",
        "- **Joinable.** `imdb_id` and `tmdb_id` let you combine it with other movie datasets.",
        "- **Kept up to date.** Rebuilt weekly, so new releases and corrections arrive automatically.",
        "",
        "## Files",
        "",
        files_markdown(tables_written),
        "",
        "## Which films are included",
        "",
        f"Feature films with a Wikipedia article in at least {MIN_SITELINKS} languages. This keeps the "
        "films people actually know and search for, and leaves out stub entries with almost no metadata. "
        "`wikipedia_languages` can be used as a popularity measure.",
        "",
        "## Completeness",
        "",
        "Wikidata is edited by volunteers, so not every field is filled for every film. Empty means "
        "\"not recorded\", not zero. Money columns only use values recorded in US dollars (not adjusted for "
        "inflation). Share of films with a value, as of this version:",
        "",
        completeness_markdown(frames.get("movies") if frames else None),
        "",
        "## Updates",
        "",
        f"Rebuilt weekly from Wikidata by an automated pipeline. Last update: {snapshot_date:%Y-%m-%d} (UTC).",
        "",
        "## Source and license",
        "",
        "Source: [Wikidata](https://www.wikidata.org), via its public SPARQL endpoint. Wikidata content is "
        "released under CC0 1.0, and so is this dataset. Credit to Wikidata and its editors is appreciated.",
    ])


SPEC = DatasetSpec(
    name="movies",
    slug="movie-metadata-genre-crew-color-tech-specs",
    title="Movie Metadata: Genre, Crew, Color & Tech Specs",
    subtitle="CC0 data on notable films: genres, directors, cast, color, aspect ratio, awards",
    license="CC0-1.0",
    keywords=["movies and tv shows", "arts and entertainment", "popular culture", "recommender systems", "tabular"],
    tables=TABLES,
    sources=(
        "Wikidata (https://www.wikidata.org), CC0, queried through https://query.wikidata.org. "
        "Built weekly by https://github.com/daniel766hi/kaggle-compe"
    ),
    make_fetchers=make_fetchers,
    describe=describe,
    cover=ASSETS / "movies-cover.png",
    update_frequency="weekly",
    run_weekday=0,
)
