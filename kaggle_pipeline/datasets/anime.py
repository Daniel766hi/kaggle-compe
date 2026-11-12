"""Anime database: every anime from the anime-offline-database, with scores, tags, studios and franchise links.

Source: manami-project/anime-offline-database (https://github.com/manami-project/anime-offline-database), released
weekly on GitHub under the Open Database License (ODbL) v1.0, with contents under the Database Contents License
(DbCL) v1.0. It merges the entries of MyAnimeList, AniList, Kitsu, AniDB, Anime-Planet, aniSearch, LiveChart,
Anime News Network, SIMKL and AnimeCountdown into one record per anime, with a score averaged over those sites.
Nothing is scraped from those sites here: the project's published release file is the only input.
"""

import json
import logging
import re
import unicodedata
from collections import Counter
from pathlib import Path

import pandas as pd

from ..http import make_session as base_session
from ..schema import Column, DatasetSpec, Table, files_markdown

log = logging.getLogger(__name__)

ASSETS = Path(__file__).resolve().parents[2] / "assets"
RELEASE = ("https://github.com/manami-project/anime-offline-database/releases/latest/download/"
           "anime-offline-database-minified.json")

# A stable id per anime: the first of its sources in this order (the source URLs are unique across entries).
SOURCE_PREFIX = [
    ("myanimelist.net/anime/", "mal"), ("anilist.co/anime/", "anilist"), ("kitsu.app/anime/", "kitsu"),
    ("anidb.net/anime/", "anidb"), ("anisearch.com/anime/", "anisearch"), ("anime-planet.com/anime/", "animeplanet"),
    ("livechart.me/anime/", "livechart"), ("animenewsnetwork.com/encyclopedia/anime.php?id=", "ann"),
    ("simkl.com/anime/", "simkl"), ("animecountdown.com/", "animecountdown"),
]
NUMERIC_IDS = {"mal": "mal_id", "anilist": "anilist_id", "kitsu": "kitsu_id", "anidb": "anidb_id"}

ANIME = Table(
    name="anime",
    kind="history",  # each weekly release is the full database; the file is rebuilt from it
    description="One row per anime (TV, movie, OVA, ONA, special): year and season, episodes, length, score, studios, tags and franchise.",
    key=("anime_id",),
    min_rows=30_000,
    max_shrink=0.02,  # the source merges and removes a few duplicate entries each release
    columns=[
        Column("anime_id", "string", "Stable id: the first source in the order mal, anilist, kitsu, anidb, ... e.g. mal-5114"),
        Column("title", "string", "Main title (usually romanized Japanese)"),
        Column("type", "string", "TV, MOVIE, OVA, ONA (web), SPECIAL or UNKNOWN"),
        Column("status", "string", "FINISHED, ONGOING, UPCOMING or UNKNOWN"),
        Column("year", "integer", "Year of first release"),
        Column("season", "string", "Season of first release: WINTER, SPRING, SUMMER, FALL (empty if unknown)"),
        Column("episodes", "integer", "Number of episodes (0 if unknown)"),
        Column("episode_minutes", "number", "Length of one episode in minutes"),
        Column("total_minutes", "number", "Episodes times episode length, in minutes"),
        Column("score", "number", "Average score across the source sites, scale 1-10 (arithmetic mean)"),
        Column("score_median", "number", "Median of the source sites' scores (1-10)"),
        Column("score_agm", "number", "Arithmetic-geometric mean of the source sites' scores (1-10)"),
        Column("studios", "string", "Animation studios, lower case without Co./Ltd./Inc., separated by |"),
        Column("producers", "string", "Producers, separated by |"),
        Column("tags", "string", "Genres and themes, separated by | (see anime_tags for one row per tag)"),
        Column("n_tags", "integer", "Number of tags"),
        Column("n_sources", "integer", "Number of sites listing this anime (a rough measure of how known it is)"),
        Column("n_synonyms", "integer", "Number of alternative titles"),
        Column("franchise_id", "string", "Franchise: anime_id of its earliest entry (related titles sharing a first word)"),
        Column("franchise_size", "integer", "Number of anime in the franchise"),
        Column("mal_id", "integer", "MyAnimeList id"),
        Column("anilist_id", "integer", "AniList id"),
        Column("kitsu_id", "integer", "Kitsu id"),
        Column("anidb_id", "integer", "AniDB id"),
        Column("picture", "string", "URL of the poster image (hosted by the source site)"),
    ],
)

TAGS = Table(
    name="anime_tags",
    kind="history",
    description="One row per anime and tag (genres and themes such as comedy, isekai, mecha, based on a manga).",
    key=("anime_id", "tag"),
    min_rows=300_000,
    max_shrink=0.05,
    columns=[
        Column("anime_id", "string", "Anime (joins anime.anime_id)"),
        Column("tag", "string", "Tag, lower case"),
    ],
)

RELATIONS = Table(
    name="anime_relations",
    kind="history",
    description="Links between related anime (sequels, prequels, side stories, spin-offs), as pairs of anime_id.",
    key=("anime_id", "related_id"),
    min_rows=50_000,
    max_shrink=0.05,
    columns=[
        Column("anime_id", "string", "Anime (joins anime.anime_id)"),
        Column("related_id", "string", "A related anime (joins anime.anime_id)"),
    ],
)

STUDIOS = Table(
    name="studios",
    kind="derived",
    description="One row per animation studio: titles, active years, scores and the tags it uses most.",
    key=("studio",),
    min_rows=0,
    columns=[
        Column("studio", "string", "Studio name, lower case, company suffixes (Co., Ltd., Inc.) removed"),
        Column("titles", "integer", "Anime the studio worked on"),
        Column("tv_titles", "integer", "Of which TV series"),
        Column("first_year", "integer", "Year of its first title"),
        Column("last_year", "integer", "Year of its latest title"),
        Column("titles_last_5y", "integer", "Titles first released in the last 5 complete years"),
        Column("scored_titles", "integer", "Titles with a score"),
        Column("mean_score", "number", "Mean score of its scored titles (1-10)"),
        Column("best_title", "string", "Its highest-scored title among those listed on 3 or more sites"),
        Column("top_tags", "string", "Its 5 most frequent tags, separated by |"),
    ],
)

SEASONS = Table(
    name="seasons",
    kind="derived",
    description="One row per year and season: how many anime came out, by type, and their mean score.",
    key=("year", "season"),
    min_rows=0,
    columns=[
        Column("year", "integer", "Year"),
        Column("season", "string", "WINTER, SPRING, SUMMER, FALL, or UNDEFINED when the source has no season"),
        Column("titles", "integer", "Anime first released"),
        Column("tv", "integer", "Of which TV series"),
        Column("movies", "integer", "Of which movies"),
        Column("ona", "integer", "Of which ONA (web releases)"),
        Column("ova_special", "integer", "Of which OVA and specials"),
        Column("mean_score_tv", "number", "Mean score of the TV series (1-10)"),
    ],
)

TAG_TRENDS = Table(
    name="tag_trends",
    kind="derived",
    description="One row per tag used on 50+ anime: how common it is per decade, its mean score and its growth.",
    key=("tag",),
    min_rows=0,
    columns=[
        Column("tag", "string", "Tag"),
        Column("titles", "integer", "Anime with this tag"),
        Column("mean_score", "number", "Mean score of scored anime with this tag (1-10)"),
        Column("share_1990s_pct", "number", "Share of 1990-1999 anime with this tag (%)"),
        Column("share_2000s_pct", "number", "Share of 2000-2009 anime with this tag (%)"),
        Column("share_2010s_pct", "number", "Share of 2010-2019 anime with this tag (%)"),
        Column("share_2020s_pct", "number", "Share of anime from 2020 on with this tag (%)"),
        Column("growth_2010s_to_2020s", "number", "Share in the 2020s divided by share in the 2010s (>1: more common now)"),
    ],
)

TABLES = [ANIME, TAGS, RELATIONS, STUDIOS, SEASONS, TAG_TRENDS]

# ---------- download and parsing ----------


def make_session():
    return base_session()


def download(session):
    resp = session.get(RELEASE, timeout=600)
    resp.raise_for_status()
    db = json.loads(resp.content)
    log.info("anime-offline-database: %d entries, last update %s", len(db.get("data", [])), db.get("lastUpdate"))
    return db


def source_id(url):
    """('mal', '5114') for a MyAnimeList URL, and so on; (None, None) for an unknown site."""
    url = re.sub(r"^https?://(www\.)?", "", url)
    for prefix, short in SOURCE_PREFIX:
        if url.startswith(prefix):
            return short, url[len(prefix):].strip("/")
    return None, None


COMPANY_SUFFIX = re.compile(r"(,?\s+(co\.?|ltd\.?|inc\.?|llc|corp\.?|corporation|k\.k\.|co\., ltd\.))+$")


def company(name):
    """'Toei Animation Co., Ltd.' and 'toei animation' -> 'toei animation'."""
    name = re.sub(r"\s+", " ", str(name).strip().lower())
    return COMPANY_SUFFIX.sub("", name).strip(" ,") or name


def companies(names):
    seen = []
    for n in names or []:
        c = company(n)
        if c not in seen:
            seen.append(c)
    return "|".join(seen) or None


def anime_id(sources):
    found = {}
    for url in sources:
        short, value = source_id(url)
        if not short or not value:
            continue
        if short in NUMERIC_IDS and value.isdigit():
            # A few entries list two MyAnimeList ids; keep the lowest so the id stays the same between releases.
            if short not in found or int(value) < int(found[short]):
                found[short] = value
        else:
            found.setdefault(short, value)
    for _, short in SOURCE_PREFIX:
        if short in found:
            return f"{short}-{found[short]}", found
    return None, found


class Franchises:
    """Union-find over the relation links; each franchise is named after its earliest entry."""

    def __init__(self, ids):
        self.parent = {i: i for i in ids}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def parse(db):
    """The release file -> (anime, tags, relations) DataFrames."""
    entries = db["data"]
    rows, url_to_id = [], {}
    for e in entries:
        aid, ids = anime_id(e.get("sources", []))
        if not aid:
            continue
        for url in e.get("sources", []):
            url_to_id[url] = aid
        season = e.get("animeSeason") or {}
        duration = e.get("duration") or {}
        minutes = duration.get("value") / 60 if duration.get("unit") == "SECONDS" and duration.get("value") else None
        # Sites let people rate announced titles; those numbers measure anticipation, not the show, so drop them.
        score = {} if e.get("status") == "UPCOMING" else (e.get("score") or {})
        episodes = e.get("episodes") or 0
        rows.append({
            "anime_id": aid, "title": e.get("title"), "type": e.get("type"), "status": e.get("status"),
            "year": season.get("year"),
            "season": None if season.get("season") in (None, "UNDEFINED") else season.get("season"),
            "episodes": episodes, "episode_minutes": round(minutes, 2) if minutes else None,
            "total_minutes": round(minutes * episodes, 1) if minutes and episodes else None,
            "score": round(score["arithmeticMean"], 3) if score.get("arithmeticMean") else None,
            "score_median": round(score["median"], 3) if score.get("median") else None,
            "score_agm": round(score["arithmeticGeometricMean"], 3) if score.get("arithmeticGeometricMean") else None,
            "studios": companies(e.get("studios")), "producers": companies(e.get("producers")),
            "tags": "|".join(e.get("tags") or []) or None, "n_tags": len(e.get("tags") or []),
            "n_sources": len(e.get("sources") or []), "n_synonyms": len(e.get("synonyms") or []),
            **{col: int(ids[short]) if ids.get(short, "").isdigit() else None for short, col in NUMERIC_IDS.items()},
            "picture": e.get("picture"), "_related": e.get("relatedAnime") or [], "_tags": e.get("tags") or [],
        })
    anime = pd.DataFrame(rows).drop_duplicates("anime_id")

    tags = anime[["anime_id", "_tags"]].explode("_tags").dropna().rename(columns={"_tags": "tag"})
    tags = tags.drop_duplicates().reset_index(drop=True)

    rel = anime[["anime_id", "_related"]].explode("_related").dropna()
    rel["related_id"] = rel["_related"].map(url_to_id)  # links to entries outside the database are dropped
    rel = rel.dropna(subset=["related_id"])
    rel = rel[rel["anime_id"] != rel["related_id"]][["anime_id", "related_id"]].drop_duplicates().reset_index(drop=True)

    anime = add_franchises(anime.drop(columns=["_related", "_tags"]), rel)
    return anime[ANIME.column_names].reset_index(drop=True), tags, rel


GENERIC_LEADS = {"the", "a", "an", "gekijouban", "gekijou", "eiga", "movie", "shin", "zoku", "new"}


def title_stem(title):
    """First meaningful word of a title, lower case ASCII ('Gekijouban Fate/...' -> 'fate')."""
    text = unicodedata.normalize("NFKD", str(title or "")).encode("ascii", "ignore").decode().lower()
    words = re.findall(r"[a-z0-9]+", text)
    while len(words) > 1 and words[0] in GENERIC_LEADS:
        words = words[1:]
    return words[0] if words else ""


def add_franchises(anime, rel):
    """Group entries joined by relation links whose titles start with the same word.

    Following every link chains unrelated series together through crossovers and collaboration shorts (one group
    of 5,000+ anime); requiring a shared first word keeps sequels, movies and spin-offs of one series together.
    """
    uf = Franchises(anime["anime_id"])
    stem = dict(zip(anime["anime_id"], anime["title"].map(title_stem)))
    for a, b in zip(rel["anime_id"], rel["related_id"]):
        if len(stem.get(a, "")) >= 3 and stem.get(a) == stem.get(b):
            uf.union(a, b)
    root = anime["anime_id"].map(uf.find)
    # Name each franchise after its earliest entry (ties: the one listed on most sites, then by id), so the
    # name does not depend on link order.
    order = anime.assign(_root=root, _y=anime["year"].fillna(9999), _n=-anime["n_sources"]).sort_values(
        ["_root", "_y", "_n", "anime_id"])
    first = order.groupby("_root")["anime_id"].first()
    anime["franchise_id"] = root.map(first)
    anime["franchise_size"] = anime.groupby("franchise_id")["anime_id"].transform("size")
    return anime


def make_fetchers(_, snapshot_date):
    session = make_session()
    cache = {}

    def parsed():
        if "x" not in cache:
            cache["x"] = parse(download(session))
        return cache["x"]

    return {
        "anime": lambda previous: parsed()[0],
        "anime_tags": lambda previous: parsed()[1],
        "anime_relations": lambda previous: parsed()[2],
    }


# ---------- derived ----------


def last_complete_year(anime):
    """The latest year with released titles that is fully over (upcoming entries can have future years)."""
    finished = anime.loc[anime["status"] == "FINISHED", "year"].dropna()
    return int(finished.max()) - 1 if not finished.empty else None


def studios(anime):
    if anime is None or anime.empty:
        return pd.DataFrame(columns=STUDIOS.column_names)
    a = anime.dropna(subset=["studios"]).assign(studio=lambda d: d["studios"].str.split("|")).explode("studio")
    cutoff = (last_complete_year(anime) or 0) - 4
    rows = []
    for studio, d in a.groupby("studio"):
        scored = d.dropna(subset=["score"])
        known = scored[scored["n_sources"] >= 3]
        tags = Counter(t for ts in d["tags"].dropna() for t in ts.split("|"))
        rows.append({
            "studio": studio, "titles": len(d), "tv_titles": int((d["type"] == "TV").sum()),
            "first_year": d["year"].min(), "last_year": d["year"].max(),
            "titles_last_5y": int(((d["year"] >= cutoff) & (d["year"] <= cutoff + 4)).sum()),
            "scored_titles": len(scored), "mean_score": round(scored["score"].mean(), 3) if len(scored) else None,
            "best_title": known.loc[known["score"].idxmax(), "title"] if len(known) else None,
            "top_tags": "|".join(t for t, _ in tags.most_common(5)) or None,
        })
    return pd.DataFrame(rows).sort_values("titles", ascending=False)[STUDIOS.column_names].reset_index(drop=True)


def seasons(anime):
    if anime is None or anime.empty:
        return pd.DataFrame(columns=SEASONS.column_names)
    a = anime.dropna(subset=["year"]).assign(season=lambda d: d["season"].fillna("UNDEFINED"))
    g = a.groupby(["year", "season"])
    out = pd.DataFrame({
        "titles": g.size(), "tv": g["type"].apply(lambda s: int((s == "TV").sum())),
        "movies": g["type"].apply(lambda s: int((s == "MOVIE").sum())), "ona": g["type"].apply(lambda s: int((s == "ONA").sum())),
        "ova_special": g["type"].apply(lambda s: int(s.isin(["OVA", "SPECIAL"]).sum())),
    }).reset_index()
    tv = a[a["type"] == "TV"].groupby(["year", "season"])["score"].mean().round(3).rename("mean_score_tv").reset_index()
    out = out.merge(tv, on=["year", "season"], how="left")
    order = {"WINTER": 0, "SPRING": 1, "SUMMER": 2, "FALL": 3, "UNDEFINED": 4}
    out = out.sort_values(["year", "season"], key=lambda s: s.map(order) if s.name == "season" else s)
    return out[SEASONS.column_names].reset_index(drop=True)


def tag_trends(anime, tags, min_titles=50):
    if anime is None or anime.empty or tags is None or tags.empty:
        return pd.DataFrame(columns=TAG_TRENDS.column_names)
    decade = pd.cut(anime["year"], [1989, 1999, 2009, 2019, 9999], labels=["1990s", "2000s", "2010s", "2020s"])
    a = anime.assign(decade=decade)[["anime_id", "decade", "score"]]
    per_decade = a["decade"].value_counts()
    t = tags.merge(a, on="anime_id", how="left")
    counts = t.groupby("tag").size()
    keep = counts[counts >= min_titles].index
    t = t[t["tag"].isin(keep)]
    shares = (t.groupby(["tag", "decade"], observed=False).size().unstack(fill_value=0) / per_decade * 100).round(2)
    out = pd.DataFrame({"titles": counts[keep], "mean_score": t.groupby("tag")["score"].mean().round(3)})
    for d in ("1990s", "2000s", "2010s", "2020s"):
        out[f"share_{d}_pct"] = shares[d] if d in shares else 0.0
    out["growth_2010s_to_2020s"] = (out["share_2020s_pct"] / out["share_2010s_pct"]).round(3).where(out["share_2010s_pct"] > 0)
    return out.reset_index().rename(columns={"index": "tag"}).sort_values("titles", ascending=False)[TAG_TRENDS.column_names].reset_index(drop=True)


def derive(frames):
    anime, tags = frames.get("anime"), frames.get("anime_tags")
    return {"studios": studios(anime), "seasons": seasons(anime), "tag_trends": tag_trends(anime, tags)}


# ---------- description ----------


def overview_markdown(frames):
    anime = (frames or {}).get("anime")
    if anime is None or anime.empty:
        return "(computed when the dataset is built)"
    types = anime["type"].value_counts()
    scored = anime["score"].notna().sum()
    franchises = anime.loc[anime["franchise_size"] > 1, "franchise_id"].nunique()
    lines = [
        f"- **{len(anime):,} anime** from {int(anime['year'].min())} to {int(anime['year'].max())} "
        f"(including announced titles): {types.get('TV', 0):,} TV series, {types.get('MOVIE', 0):,} movies, "
        f"{types.get('ONA', 0):,} web series (ONA), {types.get('OVA', 0):,} OVAs and {types.get('SPECIAL', 0):,} specials.",
        f"- **{scored:,} with a score** averaged over the sites that list them; "
        f"{anime['tags'].notna().sum():,} with tags ({(frames or {}).get('anime_tags', pd.DataFrame()).shape[0]:,} tag rows).",
        f"- **{franchises:,} franchises** with two or more entries, built from {len((frames or {}).get('anime_relations', [])):,} "
        "relation links.",
    ]
    top = anime[(anime["n_sources"] >= 6) & (anime["type"] == "TV")].nlargest(5, "score")
    if not top.empty:
        lines += ["", "Highest-scored TV series listed on 6+ sites:", "", "| Title | Year | Score |", "|---|---|---|"]
        lines += [f"| {r.title} | {int(r.year) if pd.notna(r.year) else ''} | {r.score:.2f} |" for r in top.itertuples()]
    return "\n".join(lines)


def describe(snapshot_date, tables_written, frames=None):
    return "\n".join([
        "**A clean, analysis-ready database of every anime**: TV series, movies, OVAs, web series and specials "
        "from the first Japanese animation to announced titles, with release year and season, episodes and running time, an average "
        "score across up to ten anime sites, studios, producers, genres and themes, and links between sequels "
        "and spin-offs grouped into franchises.",
        "",
        "## Why this dataset",
        "",
        "- **One record per anime, merged across sites**: MyAnimeList, AniList, Kitsu, AniDB, Anime-Planet, aniSearch, "
        "LiveChart, Anime News Network, SIMKL and AnimeCountdown, with each site's id kept for joining.",
        "- **Open license**: built from the anime-offline-database (ODbL), not scraped from those sites, so it can "
        "be shared and reused with attribution.",
        "- **Ready for analysis**: tidy tags table, a franchise network, and summaries by studio, season and tag "
        "trend, for recommender systems, trend analysis or network analysis.",
        "",
        "## Files",
        "",
        files_markdown(tables_written),
        "",
        "## Overview",
        "",
        overview_markdown(frames),
        "",
        "## How to read it",
        "",
        "- **Scores** average the scores the source sites publish (rescaled to 1-10). They describe the users of "
        "those sites, mostly international fans, and are missing for titles too obscure or too new to be rated.",
        "- **n_sources** counts how many sites list an anime; it is a rough proxy for how well known it is. For "
        "rankings, filter to titles on several sites so that a few votes cannot top the list.",
        "- **Franchises** group entries linked as sequel, prequel, side story or spin-off whose titles start with "
        "the same word (ignoring words like 'Gekijouban'). Following every link would chain unrelated series "
        "together through crossovers; the trade-off is that a series whose titles change (e.g. 'Pocket Monsters' "
        "vs 'Pokemon') can be split in two. `anime_relations` keeps every link for your own grouping.",
        "- **Upcoming titles have no score**: ratings of announced shows measure anticipation, not the show.",
        "- **Studio names** are lower case with company suffixes removed, so 'Toei Animation Co., Ltd.' and "
        "'toei animation' count as one studio.",
        "- **Years** are of first release; announced titles can carry future years, and some entries have no year.",
        "",
        "## Updates",
        "",
        f"Rebuilt weekly from the latest release of the anime-offline-database. Last update: {snapshot_date:%Y-%m-%d} (UTC).",
        "",
        "## Source and license",
        "",
        "Data from the anime-offline-database by manami-project (https://github.com/manami-project/anime-offline-database), "
        "made available under the Open Database License (ODbL) v1.0 (https://opendatacommons.org/licenses/odbl/1-0/); "
        "the contents are under the Database Contents License (DbCL) v1.0. This dataset is a derived database and is "
        "shared under the same ODbL v1.0: attribute the anime-offline-database when you use it, and share databases "
        "you derive from it under the ODbL. Poster image URLs point to the source sites, which own those images. "
        "Not affiliated with any of the sites listed.",
    ])


SPEC = DatasetSpec(
    name="anime",
    slug="anime-database-scores-studios-tags-franchises",
    title="Anime Database: 41k Titles, Scores & Studios",
    subtitle="Every anime with scores, tags, studios, seasons and franchise links, weekly",
    license="ODbL-1.0",
    keywords=["movies and tv shows", "arts and entertainment", "popular culture", "recommender systems", "tabular"],
    tables=TABLES,
    sources=("anime-offline-database by manami-project (https://github.com/manami-project/anime-offline-database), "
             "ODbL v1.0 / DbCL v1.0. Built weekly by https://github.com/daniel766hi/kaggle-compe"),
    make_fetchers=make_fetchers,
    derive=derive,
    describe=describe,
    cover=ASSETS / "anime-cover.png",
    update_frequency="weekly",
    run_weekday=1,  # Tuesday: the source publishes its weekly release around the weekend
)
