"""Offline tests for the Indonesian Wikipedia dataset, with a fake Wikimedia pageviews API."""

import json
from datetime import date
from urllib.parse import unquote

import dataclasses

import pandas as pd
import pytest

from kaggle_pipeline import pipeline
from kaggle_pipeline.datasets import idn_wiki as wk

FIRST = date(2026, 1, 1)


class FakeWikimedia:
    """Top lists, per-article series and totals built from {(article, date): views}. The top lists
    hold top_n pages (the real API: 1,000), so pages with few views fall outside them."""

    def __init__(self, views, last_day, top_n=31):
        self.views, self.last_day, self.top_n, self.calls = views, pd.Timestamp(last_day), top_n, []

    def get(self, url, timeout=None, params=None):
        self.calls.append(url)
        parts = url.split("/")
        if "/top/" in url:
            day = pd.Timestamp(f"{parts[-3]}-{parts[-2]}-{parts[-1]}")
            if day > self.last_day:
                return self._resp(404, {})
            ranked = sorted(((v, a) for (a, d), v in self.views.items() if d == day), reverse=True)[:self.top_n]
            arts = [{"article": a, "views": v, "rank": i + 1} for i, (v, a) in enumerate(ranked)]
            return self._resp(200, {"items": [{"articles": arts}]})
        if "/per-article/" in url:
            article = unquote(parts[-4])
            start, end = pd.Timestamp(parts[-2][:8]), pd.Timestamp(parts[-1][:8])
            items = [{"timestamp": f"{d:%Y%m%d}00", "views": v} for (a, d), v in sorted(self.views.items())
                     if a == article and start <= d <= end and v > 0]
            return self._resp(200 if items else 404, {"items": items})
        if "/aggregate/" in url:
            days = pd.date_range(FIRST, self.last_day)
            return self._resp(200, {"items": [{"timestamp": f"{d:%Y%m%d}00", "views": 1000} for d in days]})
        raise AssertionError(url)

    @staticmethod
    def _resp(code, body):
        def raise_for_status(self):
            if code >= 400:
                raise RuntimeError(code)
        return type("R", (), {"status_code": code, "json": lambda self: body, "raise_for_status": raise_for_status})()


def world(last_day=date(2026, 2, 10)):
    """30 always-popular articles, plus 'Gempa_Bumi' which spikes on 20 Jan and fades."""
    days = pd.date_range(FIRST, last_day)
    views = {}
    for d in days:
        for i in range(30):
            views[(f"Artikel_{i}", d)] = 5000 - i * 100
        views[("Halaman_Utama", d)] = 90000
    for k, d in enumerate(pd.date_range("2026-01-20", last_day)):
        views[("Gempa_Bumi", d)] = int(20000 / (k + 1))
    views[("Gempa_Bumi", pd.Timestamp("2026-01-15"))] = 10  # tiny views before: outside the top list
    return views


@pytest.fixture(autouse=True)
def short_history(monkeypatch):
    monkeypatch.setattr(wk, "FIRST_DAY", FIRST)


def test_is_article_flags_namespaces_and_the_main_page_only():
    flags = wk.is_article(["Avengers:_Endgame", "Istimewa:Pencarian", "Halaman_Utama", "Joko_Widodo", "Berkas:X.jpg",
                           "halaman_utama"])
    assert flags.tolist() == [True, False, False, True, False, False]


def test_spikes_need_seven_quiet_days_and_fourteen_days_after():
    views = world()
    api = FakeWikimedia(views, "2026-02-10")
    shared = {}
    top = wk.fetch_top(api, None, date(2026, 2, 10), shared)
    spikes = wk.find_spikes(shared["top"], date(2026, 2, 10))
    assert spikes["article"].tolist() == ["Gempa_Bumi"]
    assert spikes["spike_date"].iloc[0] == pd.Timestamp("2026-01-20") and spikes["spike_rank"].iloc[0] == 2  # after the main page
    assert len(top) == top["date"].nunique() * 31  # 30 articles + main page each day
    # Not yet complete: with data only up to 2 Feb, 14 days after 20 Jan have not all passed.
    assert wk.find_spikes(shared["top"], date(2026, 2, 2)).empty


def test_spike_series_fill_missing_days_with_zero_and_skip_done_spikes():
    api = FakeWikimedia(world(), "2026-02-10")
    shared = {}
    wk.fetch_top(api, None, date(2026, 2, 10), shared)
    series = wk.fetch_spike_series(api, None, date(2026, 2, 10), shared)
    s = series.set_index("day_offset")["views"]
    assert s.loc[0] == 20000 and s.loc[1] == 10000 and s.loc[-5] == 10 and s.loc[-1] == 0
    assert len(series) == len(wk.OFFSETS)
    again = wk.fetch_spike_series(api, series, date(2026, 2, 10), shared)
    assert again.empty


def test_spike_table_computes_baseline_next_week_and_half_life():
    api = FakeWikimedia(world(), "2026-02-10")
    shared = {}
    top = wk.fetch_top(api, None, date(2026, 2, 10), shared)
    series = wk.fetch_spike_series(api, None, date(2026, 2, 10), shared)
    row = wk.spike_table(series, top).iloc[0]
    assert row["views_d0"] == 20000 and row["views_p1"] == 10000
    assert row["next_7d"] == sum(int(20000 / (k + 1)) for k in range(1, 8))
    assert row["half_life_days"] == 1 and row["baseline_7d"] == round(10 / 7, 1)
    assert row["title"] == "Gempa Bumi" and row["weekday"] == 1  # 20 Jan 2026 is a Tuesday
    assert not row["one_day_burst"]


def test_a_spike_that_vanishes_the_next_day_is_flagged_as_a_burst():
    views = world()
    views.update({("Robot_Page", pd.Timestamp("2026-01-25")): 900000, ("Robot_Page", pd.Timestamp("2026-01-26")): 40})
    api = FakeWikimedia(views, "2026-02-10")
    shared = {}
    top = wk.fetch_top(api, None, date(2026, 2, 10), shared)
    table = wk.spike_table(wk.fetch_spike_series(api, None, date(2026, 2, 10), shared), top).set_index("article")
    assert table.loc["Robot_Page", "one_day_burst"] and not table.loc["Gempa_Bumi", "one_day_burst"]


def test_full_build_writes_every_file_with_column_descriptions(tmp_path, monkeypatch):
    api = FakeWikimedia(world(), "2026-02-10")
    monkeypatch.setattr(wk, "make_session", lambda: api)
    fetchers = wk.make_fetchers(None, pd.Timestamp("2026-02-11"))
    # The real totals table needs 1,000+ days; this fake world has 41.
    spec = dataclasses.replace(wk.SPEC, tables=[dataclasses.replace(t, min_rows=1) if t.name == "daily_totals" else t
                                                for t in wk.TABLES])
    report = pipeline.build(spec, tmp_path / "v1", None, pd.Timestamp("2026-02-11"), "u/s", fetchers=fetchers)
    assert not report.failed, report.failed
    meta = json.loads((tmp_path / "v1" / "dataset-metadata.json").read_text())
    assert [r["path"] for r in meta["resources"]] == [t.file_name for t in wk.TABLES]
    for resource in meta["resources"]:
        assert all(f["description"] for f in resource["schema"]["fields"]), resource["path"]
    spikes = pd.read_csv(tmp_path / "v1" / "attention_spikes.csv")
    assert spikes["article"].tolist() == ["Gempa_Bumi"]
    monthly = pd.read_csv(tmp_path / "v1" / "monthly_top_articles.csv", parse_dates=["month"])
    assert "Halaman_Utama" not in set(monthly["article"])
    assert "| Attention spikes with full series | 1 |" in meta["description"]
