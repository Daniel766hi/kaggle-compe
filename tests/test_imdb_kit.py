"""Offline tests for the IMDb SQLite builder, with tiny files in IMDb's TSV format."""

import gzip
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "imdb_kit"))
import build_imdb_sqlite as imdb  # noqa: E402

FILES = {
    "title.basics.tsv.gz": [
        "tconst\ttitleType\tprimaryTitle\toriginalTitle\tisAdult\tstartYear\tendYear\truntimeMinutes\tgenres",
        "tt0111161\tmovie\tThe Shawshank Redemption\tThe Shawshank Redemption\t0\t1994\t\\N\t142\tDrama",
        "tt0068646\tmovie\tThe Godfather\tThe Godfather\t0\t1972\t\\N\t175\tCrime,Drama",
        "tt0903747\ttvSeries\tBreaking Bad\tBreaking Bad\t0\t2008\t2013\t49\tCrime,Drama,Thriller",
        "tt9999999\tshort\t\"Quoted\" title\t\"Quoted\" title\t0\t\\N\t\\N\t\\N\t\\N",
    ],
    "title.ratings.tsv.gz": [
        "tconst\taverageRating\tnumVotes",
        "tt0111161\t9.3\t3000000", "tt0068646\t9.2\t2000000", "tt0903747\t9.5\t2200000",
    ],
    "name.basics.tsv.gz": [
        "nconst\tprimaryName\tbirthYear\tdeathYear\tprimaryProfession\tknownForTitles",
        "nm0000209\tTim Robbins\t1958\t\\N\tactor,producer\ttt0111161",
    ],
    "title.crew.tsv.gz": ["tconst\tdirectors\twriters", "tt0111161\tnm0001104\tnm0000175"],
    "title.episode.tsv.gz": ["tconst\tparentTconst\tseasonNumber\tepisodeNumber", "tt0959621\ttt0903747\t1\t1"],
    "title.principals.tsv.gz": [
        "tconst\tordering\tnconst\tcategory\tjob\tcharacters",
        "tt0111161\t1\tnm0000209\tactor\t\\N\t[\"Andy Dufresne\"]",
        "tt0111161\t2\tnm0000151\tactor\t\\N",  # malformed line: skipped
    ],
    "title.akas.tsv.gz": [
        "titleId\tordering\ttitle\tregion\tlanguage\ttypes\tattributes\tisOriginalTitle",
        "tt0111161\t1\tUmbal Kebebasan\tID\t\\N\t\\N\t\\N\t0",
    ],
}


def write_files(folder):
    for name, lines in FILES.items():
        with gzip.open(folder / name, "wt", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


def test_builds_core_tables_views_and_genres(tmp_path):
    write_files(tmp_path)
    db = tmp_path / "imdb.sqlite"
    counts = imdb.build(db, imdb.CORE, base_url=str(tmp_path), log=lambda *a: None)
    assert counts["title_basics"] == 4 and counts["title_principals"] == 1  # malformed line skipped
    con = sqlite3.connect(db)
    row = con.execute("SELECT start_year, end_year, runtime_minutes, decade FROM title_basics "
                      "WHERE tconst = 'tt0111161'").fetchone()
    assert row == (1994, None, 142, 1990)  # \N -> NULL, numbers stored as numbers
    assert con.execute("SELECT primary_title FROM title_basics WHERE tconst = 'tt9999999'").fetchone() == (
        '"Quoted" title',)
    genres = con.execute("SELECT genre FROM title_genres WHERE tconst = 'tt0903747' ORDER BY genre").fetchall()
    assert [g for (g,) in genres] == ["Crime", "Drama", "Thriller"]
    top = con.execute("SELECT primary_title FROM top_rated_movies").fetchall()
    assert [t for (t,) in top] == ["The Shawshank Redemption", "The Godfather"]
    assert con.execute("SELECT primary_title FROM top_rated_tv").fetchone() == ("Breaking Bad",)
    assert con.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'title_akas'").fetchone() == (0,)


def test_all_tables_include_akas(tmp_path):
    write_files(tmp_path)
    counts = imdb.build(tmp_path / "all.sqlite", list(imdb.TABLES), base_url=str(tmp_path), log=lambda *a: None)
    assert counts["title_akas"] == 1


def test_a_changed_file_layout_fails_loudly(tmp_path):
    write_files(tmp_path)
    with gzip.open(tmp_path / "title.ratings.tsv.gz", "wt") as f:
        f.write("tconst\taverageRating\n")
    try:
        imdb.build(tmp_path / "x.sqlite", ["title_ratings"], base_url=str(tmp_path), log=lambda *a: None)
    except ValueError as exc:
        assert "expected 3 columns" in str(exc)
    else:
        raise AssertionError("a changed header must raise")
