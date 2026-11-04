"""Offline tests for the art museums dataset, with small files in each museum's real format."""

import dataclasses
import json

import pandas as pd
import pytest

from kaggle_pipeline import pipeline
from kaggle_pipeline.datasets import art_museums as am

MOMA = (
    "﻿Title,Artist,ConstituentID,ArtistBio,Nationality,BeginDate,EndDate,Gender,Date,Medium,Dimensions,"
    "CreditLine,AccessionNumber,Classification,Department,DateAcquired,Cataloged,ObjectID,URL,ImageURL,OnView\n"
    '"The Starry Night",Vincent van Gogh,2206,"(Dutch, 1853–1890)",(Dutch),(1853),(1890),(male),1889,Oil on canvas,'
    '"29 x 36 1/4""",Acquired through the Lillie P. Bliss Bequest,472.1941,Painting,Painting & Sculpture,1941-01-01,Y,'
    '79802,https://www.moma.org/collection/works/79802,https://www.moma.org/media/x.jpg,Gallery 501\n'
    '"Untitled",Unidentified photographer,9999,,(),(0),(0),(),c. 1920-25,Gelatin silver print,"4 x 5""",Gift,1.2020,'
    'Photograph,Photography,2020-03-02,Y,5,https://www.moma.org/collection/works/5,,\n'
    '"Maman","Louise Bourgeois, Jean-Louis Bourgeois","7712, 8001","(American, 1911–2010)","(American) (French)",'
    '"(1911) (1941)","(2010) (0)","(female) (male)",1999,Bronze,"30 ft",Gift,2.2005,Sculpture,Painting & Sculpture,'
    '2005-06-01,Y,6,https://www.moma.org/collection/works/6,,\n'
)
MET_HEADER = ("﻿Object Number,Is Highlight,Is Timeline Work,Is Public Domain,Object ID,Gallery Number,Department,"
              "AccessionYear,Object Name,Title,Culture,Period,Dynasty,Reign,Portfolio,Constituent ID,Artist Role,"
              "Artist Prefix,Artist Display Name,Artist Display Bio,Artist Suffix,Artist Alpha Sort,Artist Nationality,"
              "Artist Begin Date,Artist End Date,Artist Gender,Artist ULAN URL,Artist Wikidata URL,Object Date,"
              "Object Begin Date,Object End Date,Medium,Dimensions,Credit Line,Geography Type,City,State,County,"
              "Country,Region,Subregion,Locale,Locus,Excavation,River,Classification,Rights and Reproduction,"
              "Link Resource,Object Wikidata URL,Metadata Date,Repository,Tags,Tags AAT URL,Tags Wikidata URL\n")


def met_row(oid, title, artist, gender, nat, begin, obj_begin, accession, pd_flag, gallery):
    cells = {"Object Number": f"{oid}.1", "Is Highlight": "False", "Is Public Domain": pd_flag, "Object ID": oid,
             "Gallery Number": gallery, "Department": "European Paintings", "AccessionYear": accession,
             "Object Name": "Painting", "Title": title, "Artist Display Name": artist, "Artist Nationality": nat,
             "Artist Begin Date": begin, "Artist Gender": gender, "Object Date": obj_begin,
             "Object Begin Date": obj_begin, "Object End Date": obj_begin, "Medium": "Oil on canvas",
             "Classification": "Paintings", "Link Resource": f"http://www.metmuseum.org/art/collection/search/{oid}"}
    header = MET_HEADER.lstrip("﻿").strip().split(",")
    return ",".join(f'"{cells.get(h, "")}"' for h in header) + "\n"


MET = (MET_HEADER
       + met_row("436535", "Wheat Field with Cypresses", "Vincent van Gogh", "", "Dutch", "1853      ", "1889", "1993",
                 "True", "822")
       + met_row("10", "Self-Portrait", "Élisabeth Louise Vigée Le Brun|Studio", "Female|", "French|", "1755|", "1781",
                 "1954", "True", "")
       + met_row("11", "Amulet", "", "", "", "", "-1295", "2056", "False", ""))
CMA = (
    "﻿id,accession_number,share_license_status,title,creation_date,creation_date_earliest,creation_date_latest,"
    "artists_tags,culture,technique,department,type,measurements,creditline,current_location,url,creators,image_web\n"
    '74228,2020.113,CC0,Fishmarket,1902,1902,1902,"[\'Jewish artists\', \'male\']","France, 20th century",'
    'oil on canvas,Modern European Painting and Sculpture,Painting,66 x 81 cm,Keithley Gift,211 Fabergé,'
    'https://clevelandart.org/art/2020.113,"Camille Pissarro (French, 1830–1903), artist",https://cdn/x.jpg\n'
    '1,1965.20,Copyrighted,Bowl,c. 1950,1945,1955,[],Japan,stoneware,Japanese Art,Ceramic,10 cm,Gift,,'
    'https://clevelandart.org/art/1965.20,"Shoji Hamada (Japanese, born 1894), potter",\n'
)


@pytest.fixture(autouse=True)
def small_files(monkeypatch):
    monkeypatch.setattr(am, "MIN_MUSEUM_ROWS", 1)


def write(tmp_path):
    paths = {"MoMA": tmp_path / "moma.csv", "The Met": tmp_path / "met.csv", "Cleveland Museum of Art": tmp_path / "cma.csv"}
    for (museum, path), text in zip(paths.items(), [MOMA, MET, CMA]):
        path.write_text(text, encoding="utf-8")
    return paths


def test_moma_first_artist_and_placeholders(tmp_path):
    df = am.tidy(am.read_moma(write(tmp_path)["MoMA"])).set_index("object_id")
    night = df.loc["79802"]
    assert (night["artist"], night["artist_gender"], night["artist_birth_year"], night["acquisition_year"]) == \
        ("Vincent van Gogh", "male", 1853, 1941)
    assert night["on_view"] and night["year_start"] == 1889
    assert pd.isna(df.loc["5", "artist"]) and pd.isna(df.loc["5", "artist_gender"])  # "Unidentified photographer"
    assert pd.isna(df.loc["5", "image_url"])  # empty in the file
    assert (df.loc["5", "year_start"], df.loc["5", "year_end"]) == (1920, 1925)
    maman = df.loc["6"]
    assert (maman["artist"], maman["artist_gender"], maman["artists_count"]) == ("Louise Bourgeois", "female", 2)


def test_met_gender_only_female_and_impossible_years_dropped(tmp_path):
    df = am.read_met(write(tmp_path)["The Met"]).set_index("object_id")
    assert pd.isna(df.loc["436535", "artist_gender"])  # The Met leaves male artists blank
    assert df.loc["10", "artist_gender"] == "female" and df.loc["10", "artists_count"] == 2
    assert df.loc["436535", "artist_birth_year"] == 1853 and df.loc["436535", "on_view"]
    assert df.loc["11", "year_start"] == -1295 and pd.isna(df.loc["11", "acquisition_year"])  # "2056": a typo
    assert df.loc["436535", "is_public_domain"] and not df.loc["11", "is_public_domain"]


def test_cleveland_creators_tags_and_accession_year(tmp_path):
    df = am.read_cma(write(tmp_path)["Cleveland Museum of Art"]).set_index("object_id")
    fish = df.loc["74228"]
    assert (fish["artist"], fish["artist_nationality"], fish["artist_birth_year"], fish["artist_death_year"]) == \
        ("Camille Pissarro", "French", 1830, 1903)
    assert (fish["artist_gender"], fish["acquisition_year"], fish["is_public_domain"], fish["on_view"]) == \
        ("male", 2020, True, True)
    bowl = df.loc["1"]
    assert bowl["artist"] == "Shoji Hamada" and pd.isna(bowl["artist_death_year"])  # "born 1894"
    assert pd.isna(bowl["artist_gender"]) and bowl["acquisition_year"] == 1965 and not bowl["is_public_domain"]


class FakeSession:
    def __init__(self, files, broken=()):
        self.files, self.broken = files, set(broken)

    def get(self, url, stream=False, timeout=None):
        museum = next(m for m, u in am.SOURCES.items() if u == url)
        data = b"" if museum in self.broken else self.files[museum].read_bytes()

        class Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def raise_for_status(self):
                if museum in self_broken:
                    raise RuntimeError("404")

            def iter_content(self, n):
                yield data

        self_broken = self.broken
        return Resp()


def test_a_failed_museum_keeps_its_previous_rows(tmp_path, monkeypatch):
    files = write(tmp_path)
    shared = {}
    first = am.fetch_artworks(FakeSession(files), None, shared)
    assert set(first["museum"]) == set(am.SOURCES)
    shared = {}
    second = am.fetch_artworks(FakeSession(files, broken={"The Met"}), first, shared)
    assert (second["museum"] == "The Met").sum() == (first["museum"] == "The Met").sum()
    assert shared["failed"] == ["The Met"]


def test_full_build_writes_every_file_with_column_descriptions(tmp_path, monkeypatch):
    files = write(tmp_path)
    monkeypatch.setattr(am, "make_session", lambda: FakeSession(files))
    # The real table needs 100,000+ objects; these files hold 8.
    spec = dataclasses.replace(am.SPEC, tables=[dataclasses.replace(t, min_rows=1) if t.name == "artworks" else t
                                                for t in am.TABLES])
    report = pipeline.build(spec, tmp_path / "v1", None, pd.Timestamp("2026-11-04"), "u/s")
    assert not report.failed, report.failed
    meta = json.loads((tmp_path / "v1" / "dataset-metadata.json").read_text())
    assert [r["path"] for r in meta["resources"]][:2] == ["artworks.parquet", "collection_snapshots.parquet"]
    for resource in meta["resources"]:
        assert all(f["description"] for f in resource["schema"]["fields"]), resource["path"]
    acq = pd.read_csv(tmp_path / "v1" / "acquisitions_by_year.csv")
    assert acq.loc[acq["museum"] == "The Met", "share_by_women"].isna().all()
    moma2005 = acq[(acq["museum"] == "MoMA") & (acq["year"] == 2005)].iloc[0]
    assert moma2005["share_by_women"] == 1.0
    artists = pd.read_csv(tmp_path / "v1" / "artists.csv").set_index("artist")
    assert artists.loc["Vincent van Gogh", "museums"] == 2 and "Unidentified photographer" not in artists.index
    snaps = pd.read_csv(tmp_path / "v1" / "collection_latest.csv")
    assert len(snaps) == 3
    assert "| **Total** | **8** |" in meta["description"]
