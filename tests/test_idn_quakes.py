"""Offline tests for the Indonesia earthquakes dataset, with USGS-shaped GeoJSON and toy land."""

import json
from datetime import date

import pandas as pd
import shapely

from kaggle_pipeline import pipeline
from kaggle_pipeline.datasets import idn_quakes as qk

# Toy land: a "Sumatra" province, a "Jawa" province and a neighbouring "Malaysia".
LAND = qk.Land(["Sumatera Barat", "Jawa Barat", None], ["Indonesia", "Indonesia", "Malaysia"],
               [shapely.box(99, -2, 102, 1), shapely.box(106, -8, 108, -6), shapely.box(100, 3, 104, 6)])


def feature(eid, when, lat, lon, mag, depth=10.0, updated=None, ids=None, kind="earthquake"):
    ms = int(pd.Timestamp(when).value // 1_000_000)
    return {"type": "Feature", "id": eid, "geometry": {"type": "Point", "coordinates": [lon, lat, depth]},
            "properties": {"mag": mag, "place": "somewhere", "time": ms,
                           "updated": int(pd.Timestamp(updated or when).value // 1_000_000),
                           "tsunami": 0, "sig": 300, "net": "us", "magType": "mww", "type": kind,
                           "status": "reviewed", "ids": ids or f",{eid},", "felt": None, "alert": None}}


class FakeUsgs:
    """Answers /count and /query from a list of features, like the FDSN service."""

    def __init__(self, features):
        self.features = features
        self.calls = []

    def _select(self, params):
        out = []
        for f in self.features:
            t = pd.to_datetime(f["properties"]["time"], unit="ms")
            u = pd.to_datetime(f["properties"]["updated"], unit="ms")
            if "starttime" in params and t < pd.Timestamp(params["starttime"]):
                continue
            if "endtime" in params and t >= pd.Timestamp(params["endtime"]):
                continue
            if "updatedafter" in params and u <= pd.Timestamp(params["updatedafter"]):
                continue
            out.append(f)
        return out

    def get(self, url, params=None, timeout=None):
        self.calls.append((url.rsplit("/", 1)[-1], dict(params or {})))
        found = self._select(params or {})
        body = {"count": len(found)} if url.endswith("/count") else {"features": found[: params.get("limit", 20000)]}
        return type("R", (), {"status_code": 200, "json": lambda self: body, "text": "",
                              "raise_for_status": lambda self: None})()


def test_to_frame_reads_geojson_and_converts_times():
    df = qk.to_frame([feature("us1", "2024-01-01 12:00", -1.0, 100.0, 6.1, depth=35.0)])
    row = df.iloc[0]
    assert row["time"] == pd.Timestamp("2024-01-01 12:00")
    assert row["time_wib"] == pd.Timestamp("2024-01-01 19:00")
    assert (row["depth_km"], row["mag"], row["ids"]) == (35.0, 6.1, "us1")


def test_land_gives_province_on_land_and_nearest_land_offshore():
    country, province, km = LAND.lookup([100.0, 97.0, 102.0], [0.0, 0.0, 7.0])
    assert list(country) == ["Indonesia", "Indonesia", "Malaysia"]
    assert list(province) == ["Sumatera Barat", "Sumatera Barat", None]
    assert km[0] == 0 and 200 < km[1] < 240  # 2 degrees west of the toy Sumatra


def test_busy_periods_are_split_below_the_usgs_limit(monkeypatch):
    monkeypatch.setattr(qk, "MAX_EVENTS", 3)
    usgs = FakeUsgs([feature(f"e{i}", f"2004-12-{26 + i % 5:02d} 0{i % 9}:00", 3.0, 95.5, 5.0) for i in range(7)])
    got = qk.fetch_period(usgs, pd.Timestamp("2004-12-01"), pd.Timestamp("2005-01-01"))
    assert sorted(f["id"] for f in got) == sorted(f"e{i}" for i in range(7))
    assert all(len(usgs._select(p)) < 3 for name, p in usgs.calls if name == "query")


def test_later_runs_fetch_updated_events_and_drop_merged_ids():
    usgs = FakeUsgs([feature("us1", "2020-05-01", -1.0, 100.0, 5.0), feature("us2", "2021-05-01", -7.0, 107.0, 6.0)])
    first = qk.fetch_events(usgs, None, date(2026, 10, 1), land=LAND)
    assert sorted(first["id"]) == ["us1", "us2"] and set(first["province"]) == {"Sumatera Barat", "Jawa Barat"}
    # USGS revises us1's magnitude and merges us2 into a new preferred id, "at2".
    usgs.features = [feature("us1", "2020-05-01", -1.0, 100.0, 5.3, updated="2026-10-02"),
                     feature("at2", "2021-05-01", -7.0, 107.0, 6.1, updated="2026-10-02", ids=",at2,us2,"),
                     feature("us3", "2026-10-02", -6.5, 107.5, 4.8, updated="2026-10-02")]
    second = qk.fetch_events(usgs, first, date(2026, 10, 2), land=LAND).set_index("id")
    assert sorted(second.index) == ["at2", "us1", "us3"]
    assert second.loc["us1", "mag"] == 5.3
    assert any("updatedafter" in p for _, p in usgs.calls)


def test_sequences_count_aftershocks_in_the_radius_and_flag_prior_larger():
    t0 = pd.Timestamp("2018-08-05 11:46")
    events = qk.to_frame([
        feature("main", t0, -8.3, 116.4, 6.9),
        feature("a1", t0 + pd.Timedelta(hours=3), -8.35, 116.5, 4.7),       # day 1
        feature("a2", t0 + pd.Timedelta(days=4), -8.4, 116.3, 5.2),          # day 4, M5+
        feature("small", t0 + pd.Timedelta(days=2), -8.3, 116.4, 4.0),      # below M4.5
        feature("far", t0 + pd.Timedelta(days=2), -2.0, 100.0, 5.5),         # elsewhere
        feature("late", t0 + pd.Timedelta(days=9), -8.3, 116.4, 5.6),        # after 7 days
        feature("fore", t0 - pd.Timedelta(days=6), -8.3, 116.5, 6.4),        # foreshock
    ])
    events["country"], events["province"] = "Indonesia", "Nusa Tenggara Barat"
    seq = qk.sequences(events).set_index("mainshock_id")
    main = seq.loc["main"]
    assert (main["aftershocks_m45_1d"], main["aftershocks_m45_7d"], main["aftershocks_m5_7d"]) == (1, 2, 1)
    assert main["aftershocks_m5_1d"] == 0 and main["max_aftershock_mag_7d"] == 5.2 and main["prior_m45_30d"] == 1
    assert not main["prior_larger_30d"] and main["complete_7d"]
    assert seq.loc["fore", "aftershocks_m45_7d"] == 2  # main and a1 follow the 6.4 within 7 days
    assert seq.loc["far", "prior_larger_30d"] == False  # noqa: E712 - 1,800 km away
    assert seq.loc["late", "prior_larger_30d"]  # the 6.9 hit 9 days earlier


def test_a_quake_inside_a_great_quakes_zone_is_flagged_even_when_far_from_its_epicentre():
    t0 = pd.Timestamp("2026-08-14 21:58")
    events = qk.to_frame([feature("great", t0, -8.0, 118.0, 7.8),            # zone radius about 140 km
                          feature("later", t0 + pd.Timedelta(minutes=15), -8.0, 119.1, 5.9)])  # 121 km east
    events["country"], events["province"] = "Indonesia", "Nusa Tenggara Timur"
    seq = qk.sequences(events).set_index("mainshock_id")
    assert seq.loc["later", "prior_larger_30d"]
    assert seq.loc["great", "aftershocks_m45_7d"] == 1


def test_full_build_writes_every_file_with_column_descriptions(tmp_path, monkeypatch):
    feats = [feature(f"e{i}", pd.Timestamp("2010-01-01") + pd.Timedelta(hours=7 * i), -1.0 + (i % 7) * 0.1,
                     100.0, 4.5 + (i % 20) / 10) for i in range(1500)]
    usgs = FakeUsgs(feats)
    monkeypatch.setattr(qk, "make_session", lambda: usgs)
    monkeypatch.setattr(qk.Land, "download", classmethod(lambda cls, session: LAND))
    report = pipeline.build(qk.SPEC, tmp_path / "v1", None, pd.Timestamp("2026-10-01"), "u/s")
    assert not report.failed, report.failed
    meta = json.loads((tmp_path / "v1" / "dataset-metadata.json").read_text())
    assert [r["path"] for r in meta["resources"]] == [t.file_name for t in qk.TABLES]
    for resource in meta["resources"]:
        assert all(f["description"] for f in resource["schema"]["fields"]), resource["path"]
    seq = pd.read_csv(tmp_path / "v1" / "aftershock_sequences.csv")
    assert len(seq) == sum(1 for i in range(1500) if 4.5 + (i % 20) / 10 >= 5.5)
    assert "| All events in the box | 1,500 |" in meta["description"]
