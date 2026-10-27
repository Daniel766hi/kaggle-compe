"""Build a SQLite database from IMDb's official non-commercial datasets.

    python build_imdb_sqlite.py --db imdb.sqlite                 # core tables (no title_akas)
    python build_imdb_sqlite.py --db imdb.sqlite --all           # also title_akas (much larger)

The files are downloaded straight from https://datasets.imdbws.com, so no IMDb data is
redistributed: whoever runs this script gets the data from IMDb under IMDb's terms
(personal and non-commercial use, https://developer.imdb.com/non-commercial-datasets/).

Standard library only. Column names are snake_case versions of IMDb's (startYear -> start_year);
"\\N" becomes NULL; years, counts and ratings are stored as numbers.
"""

import argparse
import gzip
import io
import sqlite3
import time
import urllib.request

BASE_URL = "https://datasets.imdbws.com/"
BATCH = 200_000

INT, REAL, TEXT = "INTEGER", "REAL", "TEXT"

# table -> (IMDb file, [(column, type)], primary key)
TABLES = {
    "title_basics": ("title.basics.tsv.gz", [
        ("tconst", TEXT), ("title_type", TEXT), ("primary_title", TEXT), ("original_title", TEXT),
        ("is_adult", INT), ("start_year", INT), ("end_year", INT), ("runtime_minutes", INT), ("genres", TEXT),
    ], "tconst"),
    "title_ratings": ("title.ratings.tsv.gz", [
        ("tconst", TEXT), ("average_rating", REAL), ("num_votes", INT),
    ], "tconst"),
    "name_basics": ("name.basics.tsv.gz", [
        ("nconst", TEXT), ("primary_name", TEXT), ("birth_year", INT), ("death_year", INT),
        ("primary_profession", TEXT), ("known_for_titles", TEXT),
    ], "nconst"),
    "title_crew": ("title.crew.tsv.gz", [
        ("tconst", TEXT), ("directors", TEXT), ("writers", TEXT),
    ], "tconst"),
    "title_episode": ("title.episode.tsv.gz", [
        ("tconst", TEXT), ("parent_tconst", TEXT), ("season_number", INT), ("episode_number", INT),
    ], "tconst"),
    "title_principals": ("title.principals.tsv.gz", [
        ("tconst", TEXT), ("ordering", INT), ("nconst", TEXT), ("category", TEXT), ("job", TEXT),
        ("characters", TEXT),
    ], None),
    "title_akas": ("title.akas.tsv.gz", [
        ("title_id", TEXT), ("ordering", INT), ("title", TEXT), ("region", TEXT), ("language", TEXT),
        ("types", TEXT), ("attributes", TEXT), ("is_original_title", INT),
    ], None),
}
CORE = [t for t in TABLES if t != "title_akas"]

INDEXES = [
    ("title_basics", "title_type, start_year"),
    ("title_ratings", "num_votes"),
    ("title_principals", "tconst"),
    ("title_principals", "nconst"),
    ("title_principals", "category"),
    ("title_episode", "parent_tconst"),
    ("title_genres", "genre"),
    ("title_genres", "tconst"),
    ("title_akas", "title_id"),
    ("title_akas", "region"),
]

VIEWS = {
    # IMDb-style weighted rating: (v / (v + m)) * R + (m / (v + m)) * C, with m = minimum votes
    # and C = mean rating of the candidate titles.
    "top_rated_movies": """
        WITH films AS (
            SELECT b.tconst, b.primary_title, b.start_year, r.average_rating, r.num_votes
            FROM title_basics b JOIN title_ratings r USING (tconst)
            WHERE b.title_type = 'movie' AND r.num_votes >= 25000
        ), c AS (SELECT AVG(average_rating) AS mean FROM films)
        SELECT tconst, primary_title, start_year, average_rating, num_votes,
               ROUND((num_votes * 1.0 / (num_votes + 25000)) * average_rating
                     + (25000.0 / (num_votes + 25000)) * c.mean, 3) AS weighted_rating
        FROM films, c ORDER BY weighted_rating DESC LIMIT 250""",
    "top_rated_tv": """
        WITH shows AS (
            SELECT b.tconst, b.primary_title, b.start_year, b.end_year, r.average_rating, r.num_votes
            FROM title_basics b JOIN title_ratings r USING (tconst)
            WHERE b.title_type IN ('tvSeries', 'tvMiniSeries') AND r.num_votes >= 10000
        ), c AS (SELECT AVG(average_rating) AS mean FROM shows)
        SELECT tconst, primary_title, start_year, end_year, average_rating, num_votes,
               ROUND((num_votes * 1.0 / (num_votes + 10000)) * average_rating
                     + (10000.0 / (num_votes + 10000)) * c.mean, 3) AS weighted_rating
        FROM shows, c ORDER BY weighted_rating DESC LIMIT 100""",
    "genre_decade_summary": """
        SELECT g.genre, b.decade, COUNT(*) AS movies, ROUND(AVG(r.average_rating), 2) AS avg_rating,
               SUM(r.num_votes) AS total_votes
        FROM title_genres g JOIN title_basics b USING (tconst) JOIN title_ratings r USING (tconst)
        WHERE b.title_type = 'movie' AND b.decade IS NOT NULL AND r.num_votes >= 100
        GROUP BY g.genre, b.decade""",
}


def convert(value, kind):
    if value == "\\N" or value == "":
        return None
    if kind == INT:
        try:
            return int(value)
        except ValueError:
            return None
    if kind == REAL:
        try:
            return float(value)
        except ValueError:
            return None
    return value


def open_source(name, base_url=BASE_URL):
    """A text stream of one IMDb file (an http(s) URL or a local folder as base)."""
    if base_url.startswith(("http://", "https://")):
        raw = urllib.request.urlopen(base_url + name, timeout=300)
    else:
        raw = open(f"{base_url.rstrip('/')}/{name}", "rb")
    return io.TextIOWrapper(gzip.GzipFile(fileobj=raw), encoding="utf-8", newline="\n")


def rows(stream, columns):
    """Parse IMDb's TSV: tab-separated, no quoting, "\\N" for missing values."""
    header = stream.readline().rstrip("\n").split("\t")
    if len(header) != len(columns):
        raise ValueError(f"expected {len(columns)} columns, got {header}")
    kinds = [kind for _, kind in columns]
    for line in stream:
        values = line.rstrip("\n").split("\t")
        if len(values) != len(kinds):
            continue  # a handful of malformed lines exist in some dumps
        yield [convert(v, k) for v, k in zip(values, kinds)]


def load_table(con, table, base_url=BASE_URL, log=print):
    name, columns, key = TABLES[table]
    cols = ", ".join(f"{c} {k}" + (" PRIMARY KEY" if c == key else "") for c, k in columns)
    extra = ""
    if table == "title_basics":
        extra = ", decade INTEGER"
    con.execute(f"DROP TABLE IF EXISTS {table}")
    con.execute(f"CREATE TABLE {table} ({cols}{extra})")
    placeholders = ", ".join("?" * (len(columns) + (1 if extra else 0)))
    genres = []
    if table == "title_basics":
        con.execute("DROP TABLE IF EXISTS title_genres")
        con.execute("CREATE TABLE title_genres (tconst TEXT, genre TEXT)")
    start, n, batch = time.time(), 0, []
    with open_source(name, base_url) as stream:
        for row in rows(stream, columns):
            if table == "title_basics":
                year = row[5]
                row.append(year // 10 * 10 if year is not None else None)
                if row[8]:
                    genres.extend((row[0], g) for g in row[8].split(","))
            batch.append(row)
            if len(batch) >= BATCH:
                con.executemany(f"INSERT OR REPLACE INTO {table} VALUES ({placeholders})", batch)
                if genres:
                    con.executemany("INSERT INTO title_genres VALUES (?, ?)", genres)
                n += len(batch)
                batch, genres = [], []
        if batch:
            con.executemany(f"INSERT OR REPLACE INTO {table} VALUES ({placeholders})", batch)
            n += len(batch)
        if genres:
            con.executemany("INSERT INTO title_genres VALUES (?, ?)", genres)
    con.commit()
    log(f"{table:18s} {n:>12,} rows  ({time.time() - start:,.0f} s)")
    return n


def build(db_path, tables=CORE, base_url=BASE_URL, log=print):
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA journal_mode = OFF")
    con.execute("PRAGMA synchronous = OFF")
    con.execute("PRAGMA temp_store = MEMORY")
    counts = {t: load_table(con, t, base_url, log) for t in tables}
    present = set(tables) | ({"title_genres"} if "title_basics" in tables else set())
    for table, columns in INDEXES:
        if table in present:
            name = f"idx_{table}_{columns.replace(', ', '_')}"
            con.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({columns})")
    if "title_basics" in present:
        con.execute("CREATE INDEX IF NOT EXISTS idx_title_basics_decade ON title_basics (decade)")
    if {"title_basics", "title_ratings"} <= present:
        for view, sql in VIEWS.items():
            con.execute(f"DROP VIEW IF EXISTS {view}")
            con.execute(f"CREATE VIEW {view} AS {sql}")
    con.commit()
    con.execute("ANALYZE")
    con.close()
    return counts


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", default="imdb.sqlite", help="SQLite file to create")
    p.add_argument("--all", action="store_true", help="also load title_akas (alternative titles, very large)")
    p.add_argument("--tables", nargs="*", choices=sorted(TABLES), help="load only these tables")
    p.add_argument("--source", default=BASE_URL, help="base URL or local folder with the .tsv.gz files")
    args = p.parse_args()
    tables = args.tables or (list(TABLES) if args.all else CORE)
    build(args.db, tables, args.source)


if __name__ == "__main__":
    main()
