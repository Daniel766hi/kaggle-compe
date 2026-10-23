"""Offline tests for the Indonesia fire hotspots dataset, with FIRMS-shaped CSV and toy provinces."""

import json
from datetime import date

import pandas as pd
import pytest
import shapely

from kaggle_pipeline import pipeline
from kaggle_pipeline.datasets import idn_fires as fi

HEADER = "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight"


def firms_csv(rows):
    lines = [HEADER]
    for lat, lon, day, time_, conf, frp in rows:
        lines.append(f"{lat},{lon},330.5,0.4,0.37,{day},{time_},N,VIIRS,{conf},2.0NRT,290.1,{frp},D")
    return "\n".join(lines)


# Two toy "provinces": squares in Kalimantan and Sumatra.
PROVINCES = fi.Provinces(["Kalimantan Tengah", "Riau"],
                         [shapely.box(112, -3, 115, 0), shapely.box(100, 0, 103, 2)])


def test_tidy_reads_times_and_confidence():
    raw = pd.read_csv(pd.io.common.StringIO(firms_csv([(-2.1, 113.9, "2026-09-01", "0542", "h", 12.5)])),
                      dtype={"acq_time": str, "confidence": str})
    out = fi.tidy(raw, "Suomi NPP", "NRT").iloc[0]
    assert out["acq_datetime"] == pd.Timestamp("2026-09-01 05:42")
    assert out["confidence"] == "high" and out["processing"] == "NRT"


def test_provinces_assign_points_and_tolerate_the_coast():
    names = PROVINCES.lookup([113.0, 103.01, 120.0], [-2.0, 1.0, 5.0])
    assert names.tolist() == ["Kalimantan Tengah", "Riau", None]  # 0.01 deg off the coast still counts


def test_plan_uses_the_archive_where_it_exists_and_refreshes_recent_nrt():
    sats = {"Suomi NPP": (date(2026, 1, 1), "SNPP_SP", "SNPP_NRT")}
    recent, older = fi.plan(None, sats, {"SNPP_SP": date(2026, 1, 20)}, date(2026, 2, 3), recent_days=10)
    starts = {job[3]: job[2] for job in recent + older}
    assert starts[date(2026, 1, 16)] == "SP"       # 16-20 Jan: covered by the archive
    assert starts[date(2026, 1, 21)] == "NRT"      # 21-25 Jan: newer than the archive
    assert [j[3] for j in recent] == [date(2026, 1, 31), date(2026, 1, 26)]
    assert min(starts) == date(2026, 1, 1)


def test_plan_skips_chunks_already_fetched_from_the_right_source():
    sats = {"Suomi NPP": (date(2026, 1, 1), "SNPP_SP", "SNPP_NRT")}
    previous = pd.DataFrame({"satellite": ["Suomi NPP", "Suomi NPP"], "processing": ["SP", "NRT"],
                             "acq_date": pd.to_datetime(["2026-01-02", "2026-01-07"])})
    _, older = fi.plan(previous, sats, {"SNPP_SP": date(2026, 1, 20)}, date(2026, 1, 20), recent_days=0)
    starts = [job[3] for job in older]
    assert date(2026, 1, 1) not in starts          # archive data already there
    assert date(2026, 1, 6) in starts              # only NRT there, the archive now covers it


def fake_firms(monkeypatch, rows_by_source):
    monkeypatch.setattr(fi, "archive_end", lambda session, key: {"VIIRS_SNPP_SP": date(2026, 9, 30),
                                                                 "VIIRS_NOAA20_SP": date(2026, 9, 30)})
    monkeypatch.setattr(fi, "SATELLITES", {"Suomi NPP": (date(2026, 9, 21), "VIIRS_SNPP_SP", "VIIRS_SNPP_NRT")})
    calls = []

    def chunk(session, key, source, start):
        calls.append((source, start))
        rows = [r for r in rows_by_source.get(source, []) if start <= pd.Timestamp(r[2]).date() < start + pd.Timedelta(days=5)]
        return pd.read_csv(pd.io.common.StringIO(firms_csv(rows)), dtype={"acq_time": str, "confidence": str})
    monkeypatch.setattr(fi, "fetch_chunk", chunk)
    return calls


def test_fetch_drops_detections_outside_indonesia_and_archive_replaces_nrt(monkeypatch):
    fake_firms(monkeypatch, {
        "VIIRS_SNPP_SP": [(-2.0, 113.0, "2026-09-22", "0530", "n", 5.0)],
        "VIIRS_SNPP_NRT": [(-2.0, 113.0, "2026-10-02", "0530", "h", 9.0),
                           (1.5, 110.3, "2026-10-02", "0530", "n", 3.0)],  # Sarawak, Malaysia: dropped
    })
    previous = pd.DataFrame({  # an NRT row for a day the archive now covers
        "acq_date": pd.to_datetime(["2026-09-22"]), "acq_datetime": pd.to_datetime(["2026-09-22 05:31"]),
        "satellite": ["Suomi NPP"], "latitude": [-2.0], "longitude": [113.0], "province": ["Kalimantan Tengah"],
        "confidence": ["nominal"], "frp": [5.1], "processing": ["NRT"]})
    out = fi.fetch_hotspots(None, previous, date(2026, 10, 4), provinces=PROVINCES, key="k", budget_s=60)
    assert sorted(out["processing"]) == ["NRT", "SP"]   # the old NRT row is gone, replaced by SP
    assert set(out["province"]) == {"Kalimantan Tengah"}


def test_summaries_count_each_satellite_separately():
    fires = pd.DataFrame({
        "acq_date": pd.to_datetime(["2026-09-01"] * 3), "satellite": ["Suomi NPP", "Suomi NPP", "NOAA-20"],
        "province": ["Riau"] * 3, "confidence": ["high", "nominal", "high"], "frp": [10.0, 5.0, 7.0]})
    daily, monthly = fi.summaries(fires)
    row = daily.iloc[0]
    assert (row["hotspots_snpp"], row["hotspots_noaa20"], row["high_confidence_snpp"]) == (2, 1, 1)
    assert row["frp_sum_snpp"] == 15.0 and monthly.iloc[0]["hotspots"] == 2


def test_full_build_writes_every_file_with_column_descriptions(tmp_path, monkeypatch):
    rows = [(-2.0 + i * 0.001, 113.0, f"2026-09-{21 + i % 5:02d}", f"{i % 24:02d}30", "n", 4.0) for i in range(1200)]
    fake_firms(monkeypatch, {"VIIRS_SNPP_SP": rows})
    monkeypatch.setattr(fi.Provinces, "download", classmethod(lambda cls, session: PROVINCES))
    monkeypatch.setattr(fi, "map_key", lambda: "k")
    monkeypatch.setattr(fi, "make_session", lambda: None)
    report = pipeline.build(fi.SPEC, tmp_path / "v1", None, pd.Timestamp("2026-09-26"), "u/s")
    assert not report.failed, report.failed
    meta = json.loads((tmp_path / "v1" / "dataset-metadata.json").read_text())
    assert [r["path"] for r in meta["resources"]] == [t.file_name for t in fi.TABLES]
    for resource in meta["resources"]:
        assert all(f["description"] for f in resource["schema"]["fields"]), resource["path"]
    assert "| Suomi NPP | 1,200 |" in meta["description"]


def test_missing_key_is_explained(monkeypatch):
    monkeypatch.delenv("FIRMS_MAP_KEY", raising=False)
    with pytest.raises(RuntimeError, match="FIRMS_MAP_KEY"):
        fi.map_key()


def test_wait_for_quota_pauses_until_the_window_resets(monkeypatch):
    usage = iter([(4800, 5000), (4700, 5000), (100, 5000)])
    monkeypatch.setattr(fi, "key_usage", lambda session, key: next(usage))
    slept = []
    assert fi.wait_for_quota(None, "k", deadline=10_000, clock=lambda: 0, sleep=slept.append)
    assert slept == [60, 60]


def test_wait_for_quota_gives_up_when_the_budget_ends(monkeypatch):
    monkeypatch.setattr(fi, "key_usage", lambda session, key: (4900, 5000))
    assert not fi.wait_for_quota(None, "k", deadline=30, clock=lambda: 0, sleep=lambda s: None)


def test_partial_days_after_the_last_complete_day_are_not_published(monkeypatch):
    fake_firms(monkeypatch, {"VIIRS_SNPP_NRT": [(-2.0, 113.0, "2026-10-03", "0530", "h", 9.0),
                                                (-2.0, 113.1, "2026-10-04", "0530", "h", 9.0)]})  # "today"
    previous = pd.DataFrame({  # a partial day published by an earlier run
        "acq_date": pd.to_datetime(["2026-10-04"]), "acq_datetime": pd.to_datetime(["2026-10-04 05:30"]),
        "satellite": ["Suomi NPP"], "latitude": [-2.0], "longitude": [113.0], "province": ["Kalimantan Tengah"],
        "confidence": ["high"], "frp": [5.0], "processing": ["NRT"]})
    out = fi.fetch_hotspots(None, previous, date(2026, 10, 3), provinces=PROVINCES, key="k", budget_s=60)
    assert out["acq_date"].max() == pd.Timestamp("2026-10-03")
