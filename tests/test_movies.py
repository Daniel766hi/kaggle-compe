"""Offline tests for the Wikidata movie dataset, using rows shaped like SPARQL JSON results."""

import json

import pandas as pd
import pytest

from kaggle_pipeline import pipeline
from kaggle_pipeline.datasets import movies as mv

WD = "http://www.wikidata.org/entity/"


def films(n=1):
    return pd.DataFrame({
        "film_id": [f"Q{i}" for i in range(1, n + 1)],
        "wikipedia_languages": [50] * n,
        "release_date": ["2010-07-08"] * n,
    })


def rel(film, rel_name, value, label=None, when=None, ord_=None):
    row = {"film": WD + film, "rel": rel_name, "value": WD + value}
    if label:
        row["valueLabel"] = label
    if when:
        row["when"] = when
    if ord_:
        row["ord"] = ord_
    return row


def qty(film, prop, amount, unit, place=None):
    row = {"film": WD + film, "prop": prop, "amount": amount, "unit": WD + unit}
    if place:
        row["place"] = WD + place
    return row


def build(n=1, relations=(), quantities=(), reviews=(), basics=None):
    basics = basics if basics is not None else [{"film": WD + "Q1", "title": "Inception", "imdb_id": "tt1375666"}]
    return mv.build_tables(films(n), basics, list(relations), list(quantities), list(reviews))


@pytest.mark.parametrize("text,expected", [("93%", 93), ("74/100", 74), ("8.1/10", 81), ("n/a", None), ("150%", None)])
def test_parse_score(text, expected):
    assert mv.parse_score(text) == (pytest.approx(expected) if expected is not None else None)


def test_runtime_units_are_converted_to_minutes():
    out = build(quantities=[qty("Q1", "runtime", "2.5", mv.HOUR)])["movies"]
    assert out.loc[0, "runtime_min"] == 150


def test_money_uses_usd_and_prefers_worldwide():
    q = [
        qty("Q1", "box_office", "300000000", mv.USD, place="Q30"),      # US only
        qty("Q1", "box_office", "800000000", mv.USD, place=mv.WORLDWIDE),
        qty("Q1", "box_office", "900000000", "Q4916"),                   # euros: ignored
        qty("Q1", "budget", "160000000", mv.USD),
    ]
    out = build(quantities=q)["movies"]
    assert out.loc[0, "box_office_usd"] == 800_000_000
    assert out.loc[0, "budget_usd"] == 160_000_000


def test_relations_feed_joined_columns_and_long_tables():
    r = [
        rel("Q1", "genre", "Q471839", "science fiction film"),
        rel("Q1", "genre", "Q2484376", "thriller film"),
        rel("Q1", "director", "Q25191", "Christopher Nolan"),
        rel("Q1", "cinematographer", "Q1336437", "Wally Pfister"),
        rel("Q1", "color", "Q22006653", "color"),
        rel("Q1", "aspect_ratio", "Q1072624", "2.39:1"),
        rel("Q1", "cast", "Q38111", "Leonardo DiCaprio", ord_="1"),
        rel("Q1", "cast", "Q1", "No Label Actor"),
        rel("Q1", "award_won", "Q131520", "Academy Award for Best Cinematography", when="2011-02-27T00:00:00Z"),
        rel("Q1", "award_nominated", "Q102427", "Academy Award for Best Picture"),
        rel("Q1", "award_nominated", "Q131520", "Academy Award for Best Cinematography"),
        rel("Q1", "award_won", "Q1011547", "Saturn Award for Best Science Fiction Film"),
    ]
    t = build(relations=r)
    m = t["movies"].iloc[0]
    assert m["genres"] == "science fiction film|thriller film"
    assert m["directors"] == "Christopher Nolan"
    assert (m["color"], m["aspect_ratio"]) == ("color", "2.39:1")
    assert m["oscar_wins"] == 1 and m["oscar_nominations"] == 2
    assert m["n_cast"] == 2
    assert set(t["movie_crew"]["role"]) == {"director", "cinematographer"}
    assert t["movie_cast"].iloc[0]["person"] == "Leonardo DiCaprio"  # billed first
    awards = t["movie_awards"]
    assert awards[awards["outcome"] == "won"]["year"].dropna().tolist() == [2011]


def test_reviews_pick_tomatometer_and_metacritic():
    rows = [
        {"film": WD + "Q1", "score": "87%", "by": WD + mv.ROTTEN_TOMATOES, "method": WD + mv.TOMATOMETER},
        {"film": WD + "Q1", "score": "91%", "by": WD + mv.ROTTEN_TOMATOES, "method": WD + "Q999"},  # audience score
        {"film": WD + "Q1", "score": "74/100", "by": WD + mv.METACRITIC},
    ]
    m = build(reviews=rows)["movies"].iloc[0]
    assert m["rotten_tomatoes_pct"] == 87 and m["metacritic_score"] == 74


def test_full_build_writes_every_file_with_column_descriptions(tmp_path):
    big = 6000
    f = films(big)
    basics = [{"film": WD + fid, "title": f"Film {fid}"} for fid in f["film_id"]]
    r = []
    for fid in f["film_id"]:
        r += [rel(fid, "genre", "Q130232", "drama film"), rel(fid, "director", f"P{fid}", "Someone"),
              rel(fid, "screenwriter", f"W{fid}", "Writer"), rel(fid, "cast", f"A{fid}", "Actor", ord_="1"),
              rel(fid, "cast", f"B{fid}", "Actor 2", ord_="2")]
    r += [rel("Q1", "award_won", f"Q9{i}", f"Award {i}") for i in range(1200)]
    tables = mv.build_tables(f, basics, r, [], [])
    fetchers = {name: (lambda name: lambda prev: tables[name])(name) for name in tables}
    report = pipeline.build(mv.SPEC, tmp_path / "v1", None, pd.Timestamp("2026-10-12"), "u/s", fetchers=fetchers)
    assert not report.failed, report.failed
    meta = json.loads((tmp_path / "v1" / "dataset-metadata.json").read_text())
    assert [r["path"] for r in meta["resources"]] == [t.file_name for t in mv.TABLES]
    for resource in meta["resources"]:
        assert resource["description"]
        assert all(field["description"] for field in resource["schema"]["fields"]), resource["path"]
        written = pd.read_csv(tmp_path / "v1" / resource["path"], nrows=1)
        assert list(written.columns) == [field["name"] for field in resource["schema"]["fields"]]


def test_movies_may_lose_a_few_films_but_not_many(tmp_path):
    from kaggle_pipeline import storage
    table = mv.TABLES[0]
    prev = pd.DataFrame({"film_id": [f"Q{i}" for i in range(1000)]})
    storage.check_not_shrinking(prev, prev.iloc[:980], table)  # 2% fewer: fine
    with pytest.raises(ValueError):
        storage.check_not_shrinking(prev, prev.iloc[:900], table)  # 10% fewer: refused
