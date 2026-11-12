"""Offline tests for the anime dataset, with a small release file shaped like the anime-offline-database."""

import dataclasses
import json

import pandas as pd

from kaggle_pipeline import pipeline
from kaggle_pipeline.datasets import anime as an


def entry(title, sources, year, typ="TV", status="FINISHED", score=7.0, tags=("action",), studios=("MAPPA",), related=(),
          season="SPRING", episodes=12):
    return {"sources": list(sources), "title": title, "type": typ, "episodes": episodes, "status": status,
            "animeSeason": {"season": season, "year": year}, "picture": "https://cdn.example/p.jpg",
            "thumbnail": "https://cdn.example/t.jpg", "duration": {"value": 1440, "unit": "SECONDS"},
            "score": {"arithmeticGeometricMean": score, "arithmeticMean": score, "median": score} if score else None,
            "synonyms": [title.lower()], "studios": list(studios), "producers": ["Aniplex Inc."],
            "relatedAnime": list(related), "tags": list(tags)}


def release():
    mal = lambda i: f"https://myanimelist.net/anime/{i}"
    data = [
        entry("Shingeki no Kyojin", [mal(16498), "https://anilist.co/anime/16498", "https://kitsu.app/anime/7442"], 2013,
              related=[mal(25777), mal(99999)], tags=("action", "drama")),
        entry("Shingeki no Kyojin Season 2", [mal(25777)], 2017, related=[mal(16498)], score=8.5),
        entry("Gekijouban Shingeki no Kyojin", ["https://anidb.net/anime/9826"], 2014, typ="MOVIE", related=[mal(16498)]),
        # A crossover short linked to the series: related, but not the same franchise.
        entry("Animegatari x Shingeki no Kyojin Collab", ["https://anilist.co/anime/123078"], 2015, typ="SPECIAL",
              related=[mal(16498)], studios=("Toei Animation Co., Ltd.",)),
        entry("Toei Classic", [mal(1), mal(2)], 1960, studios=("toei animation",), tags=("comedy",), score=6.0),
        entry("Upcoming Show", [mal(60000)], 2027, status="UPCOMING", score=9.9, season="UNDEFINED", episodes=0),
    ]
    data += [entry(f"Filler {i}", [mal(1000 + i)], 2000 + i % 30, tags=("comedy", "vtuber" if i >= 25 else "mecha"))
             for i in range(60)]
    return {"license": {"name": "ODbL"}, "lastUpdate": "2026-07-04", "data": data}


def test_ids_prefer_myanimelist_and_keep_the_lowest_of_two():
    assert an.anime_id(["https://kitsu.app/anime/7", "https://myanimelist.net/anime/5114"])[0] == "mal-5114"
    assert an.anime_id(["https://myanimelist.net/anime/9", "https://myanimelist.net/anime/3"])[0] == "mal-3"
    assert an.anime_id(["https://anidb.net/anime/9826"])[0] == "anidb-9826"
    assert an.anime_id(["https://unknown.example/x"])[0] is None


def test_company_names_and_title_stems():
    assert an.company("Toei Animation Co., Ltd.") == an.company("toei animation") == "toei animation"
    assert an.company("Sunrise Inc.") == "sunrise" and an.company("MAPPA") == "mappa"
    assert an.title_stem("Gekijouban Shingeki no Kyojin") == "shingeki"


def test_parse_builds_tags_relations_and_franchises_without_crossovers():
    anime, tags, rel = an.parse(release())
    a = anime.set_index("anime_id")
    assert a.loc["mal-16498", "anilist_id"] == 16498 and a.loc["mal-16498", "episode_minutes"] == 24.0
    assert a.loc["mal-1", "studios"] == "toei animation"
    assert pd.isna(a.loc["mal-60000", "score"])  # no score for an announced title
    assert ("mal-16498", "mal-99999") not in set(zip(rel["anime_id"], rel["related_id"]))  # links outside are dropped
    sk = a.loc[["mal-16498", "mal-25777", "anidb-9826"]]
    assert set(sk["franchise_id"]) == {"mal-16498"} and set(sk["franchise_size"]) == {3}
    assert a.loc["anilist-123078", "franchise_size"] == 1  # the crossover stays on its own
    assert set(tags[tags["anime_id"] == "mal-16498"]["tag"]) == {"action", "drama"}


def test_derived_tables():
    anime, tags, rel = an.parse(release())
    d = an.derive({"anime": anime, "anime_tags": tags})
    toei = d["studios"].set_index("studio").loc["toei animation"]
    assert toei["titles"] == 2  # 'Toei Animation Co., Ltd.' and 'toei animation' are one studio
    trends = d["tag_trends"].set_index("tag")
    assert trends.loc["comedy", "titles"] >= 50 and "drama" not in trends.index  # under 50 titles
    s = d["seasons"]
    assert s[(s["year"] == 2013) & (s["season"] == "SPRING")]["tv"].iloc[0] == 3  # Shingeki + fillers 13 and 43


def test_full_build_writes_every_file_with_column_descriptions(tmp_path, monkeypatch):
    class Resp:
        status_code, content = 200, json.dumps(release()).encode()

        def raise_for_status(self):
            pass

    monkeypatch.setattr(an, "make_session", lambda: type("S", (), {"get": lambda self, url, timeout=None: Resp()})())
    spec = dataclasses.replace(an.SPEC, tables=[dataclasses.replace(t, min_rows=1) for t in an.TABLES])
    report = pipeline.build(spec, tmp_path / "v1", None, pd.Timestamp("2026-11-12"), "u/s")
    assert not report.failed, report.failed
    meta = json.loads((tmp_path / "v1" / "dataset-metadata.json").read_text())
    assert [r["path"] for r in meta["resources"]] == [t.file_name for t in an.TABLES]
    assert "Highest-scored TV series" in meta["description"] or "anime" in meta["description"]
