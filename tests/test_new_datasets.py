"""Tests for the Open-Meteo and exchange-rate datasets, using payloads shaped like the APIs'."""

import json
from datetime import date, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest
import requests

from kaggle_pipeline import pipeline
from kaggle_pipeline.datasets import idn_air_quality as aq
from kaggle_pipeline.datasets import idn_weather as wx
from kaggle_pipeline.datasets import idr_fx as fx
from kaggle_pipeline.datasets import open_meteo as om

D = date.fromisoformat


# ---------- Open-Meteo planning ----------

def test_plan_new_city_fetches_newest_chunk_first_then_backfills_older():
    jobs = om.plan({}, ["A"], D("2026-01-01"), D("2026-03-31"), recent_days=7, chunk_days=30)
    assert [(j.start, j.end, j.backfill) for j in jobs][:2] == [
        (D("2026-03-02"), D("2026-03-31"), False),
        (D("2026-01-31"), D("2026-03-01"), True),
    ]
    assert jobs[-1].start == D("2026-01-01")


def test_plan_existing_city_refreshes_recent_window_and_fills_gap():
    cov = {"A": (D("2026-01-01"), D("2026-03-20"))}
    jobs = om.plan(cov, ["A"], D("2026-01-01"), D("2026-03-31"), recent_days=7, chunk_days=30)
    assert [(j.start, j.end, j.backfill) for j in jobs] == [(D("2026-03-21"), D("2026-03-31"), False)]
    cov = {"A": (D("2026-01-01"), D("2026-03-30"))}
    jobs = om.plan(cov, ["A"], D("2026-01-01"), D("2026-03-31"), recent_days=7, chunk_days=30)
    assert [(j.start, j.end) for j in jobs] == [(D("2026-03-25"), D("2026-03-31"))]


def test_plan_interleaves_backfill_across_cities():
    cov = {"A": (D("2026-03-01"), D("2026-03-31")), "B": (D("2026-03-01"), D("2026-03-31"))}
    jobs = om.plan(cov, ["A", "B"], D("2026-01-01"), D("2026-03-31"), recent_days=7, chunk_days=30)
    backfill = [(j.city, j.start) for j in jobs if j.backfill]
    assert [c for c, _ in backfill] == ["A", "B", "A", "B"]


def test_job_units_follow_open_meteo_counting():
    job = om.Job("A", D("2026-01-01"), D("2026-12-31"), True)
    assert job.units(n_vars=9) == 27
    assert job.units(n_vars=11) == 54


def http_error(code, text=""):
    return requests.exceptions.HTTPError(response=SimpleNamespace(status_code=code, text=text))


def no_wait():
    return om.Pacer(clock=lambda: 0.0, sleep=lambda s: None)


def test_pacer_waits_when_minute_budget_is_full():
    now = [0.0]
    slept = []
    pacer = om.Pacer(per_minute=100, clock=lambda: now[0], sleep=lambda s: (slept.append(s), now.__setitem__(0, now[0] + s)))
    pacer.wait_for(60)
    pacer.wait_for(30)
    assert slept == []
    pacer.wait_for(30)  # 120 > 100: must wait until the first request leaves the window
    assert len(slept) == 1 and now[0] >= 60


def test_minutely_limit_is_waited_out_but_daily_limit_stops():
    jobs = [om.Job("A", D("2026-03-25"), D("2026-03-31"), False), om.Job("B", D("2026-03-25"), D("2026-03-31"), False)]
    calls = []

    def minutely_once(job):
        calls.append(job.city)
        if len(calls) == 1:
            raise om.RateLimited('{"reason": "Minutely API request limit exceeded. Please try again in one minute."}')
        return pd.DataFrame({"x": [1]})
    assert len(om.run_jobs(jobs, minutely_once, n_vars=5, pacer=no_wait())) == 2
    assert calls == ["A", "A", "B"]

    def daily(job):
        raise om.RateLimited('{"reason": "Daily API request limit exceeded. Please try again tomorrow."}')
    assert om.run_jobs(jobs, daily, n_vars=5, pacer=no_wait()).empty


def test_run_jobs_respects_budget_and_stops_on_rate_limit():
    jobs = [om.Job("A", D("2026-03-25"), D("2026-03-31"), False)] + [
        om.Job("A", D("2026-01-01") + timedelta(days=14 * i), D("2026-01-14") + timedelta(days=14 * i), True)
        for i in range(5)
    ]
    calls = []
    df = om.run_jobs(jobs, lambda j: calls.append(j) or pd.DataFrame({"x": [1]}), n_vars=5, budget=3, pacer=no_wait())
    assert len(calls) == 3 and len(df) == 3  # recent (1 unit) + 2 backfill units

    def limited(job):
        if job.backfill:
            raise http_error(429)
        return pd.DataFrame({"x": [1]})
    assert len(om.run_jobs(jobs, limited, n_vars=5, budget=100, pacer=no_wait())) == 1


def test_request_clamps_to_available_range():
    seen = []

    class Session:
        def get(self, url, params, timeout):
            seen.append(dict(params))
            if params["start_date"] < "2022-07-29":
                body = {"error": True, "reason": "Parameter 'start_date' is out of allowed range from 2022-07-29 to 2026-10-12"}
                return SimpleNamespace(status_code=400, text=json.dumps(body),
                                       raise_for_status=lambda: (_ for _ in ()).throw(http_error(400, json.dumps(body))))
            return SimpleNamespace(status_code=200, raise_for_status=lambda: None, json=lambda: {"ok": params})

    out = om.request(Session(), "u", {"start_date": "2022-07-01", "end_date": "2022-08-15"})
    assert out["ok"]["start_date"] == "2022-07-29" and out["ok"]["end_date"] == "2022-08-15"
    assert om.request(Session(), "u", {"start_date": "2022-01-01", "end_date": "2022-02-01"}) is None


# ---------- air quality ----------

def aq_payload(start, hours, offset_h=7, pm=20.0):
    times = pd.date_range(start, periods=hours, freq="h").strftime("%Y-%m-%dT%H:%M").tolist()
    hourly = {"time": times, **{name: [pm] * hours for name in aq.HOURLY}}
    return {"utc_offset_seconds": offset_h * 3600, "hourly": hourly}


def test_aq_parse_converts_local_time_to_utc():
    df = aq.parse(aq_payload("2026-10-01", 2, offset_h=9), "Jayapura")
    assert df["time_utc"].iloc[0] == pd.Timestamp("2026-09-30 15:00")
    assert df[["city", "province", "island"]].iloc[0].tolist() == ["Jayapura", "Papua", "Papua"]


def test_aq_daily_summary_and_who_flag():
    hourly = pd.concat([
        aq.parse(aq_payload("2026-10-01", 24, pm=20.0), "Jakarta"),
        aq.parse(aq_payload("2026-10-01", 24, pm=10.0), "Ambon"),
    ])
    daily = aq.daily(hourly).set_index("city")
    assert daily.loc["Jakarta", "exceeds_who_pm25"] == True  # noqa: E712
    assert daily.loc["Ambon", "exceeds_who_pm25"] == False  # noqa: E712
    assert daily.loc["Jakarta", "hours"] == 24


def aq_fetchers(day, n_hours):
    def fetch(prev):
        return pd.concat([aq.parse(aq_payload(day, n_hours), c) for c in ["Jakarta", "Medan"]])
    return {"idn_air_quality_hourly": fetch}


def test_aq_build_upserts_new_hours_and_writes_derived_files(tmp_path):
    pipeline.build(aq.SPEC, tmp_path / "v1", None, pd.Timestamp("2026-10-02"), "u/s", fetchers=aq_fetchers("2026-10-01", 600))
    pipeline.build(aq.SPEC, tmp_path / "v2", tmp_path / "v1", pd.Timestamp("2026-10-03"), "u/s",
                   fetchers=aq_fetchers("2026-10-20", 600))
    hourly = pd.read_parquet(tmp_path / "v2" / "idn_air_quality_hourly.parquet")
    assert len(hourly) == 2 * (600 + 600 - (600 - 19 * 24))  # overlap of 144 hours is upserted, not duplicated
    assert (tmp_path / "v2" / "idn_air_quality_daily.csv").exists()
    assert len(pd.read_csv(tmp_path / "v2" / "cities.csv")) == len(om.CITIES)


# ---------- weather ----------

def wx_payload(start, days, precip=2.0):
    times = pd.date_range(start, periods=days, freq="D").strftime("%Y-%m-%d").tolist()
    return {"daily": {"time": times, **{name: [precip if name == "precipitation_sum" else 25.0] * days
                                          for name in wx.DAILY}}}


def test_weather_monthly_counts_rainy_days():
    daily = pd.concat([wx.parse(wx_payload("2026-01-01", 31, precip=2.0), "Bandung"),
                       wx.parse(wx_payload("2026-02-01", 28, precip=0.0), "Bandung")])
    m = wx.monthly(daily).set_index("month")
    assert m.loc["2026-01-01", "rainy_days"] == 31 and m.loc["2026-01-01", "precipitation_total"] == 62
    assert m.loc["2026-02-01", "rainy_days"] == 0 and m.loc["2026-02-01", "days"] == 28


def test_weather_build(tmp_path):
    fetchers = {"idn_weather_daily": lambda prev: wx.parse(wx_payload("2026-09-01", 120), "Bandung")}
    report = pipeline.build(wx.SPEC, tmp_path / "v1", None, pd.Timestamp("2026-10-10"), "u/s", fetchers=fetchers)
    assert not report.failed
    meta = json.loads((tmp_path / "v1" / "dataset-metadata.json").read_text())
    assert [r["path"] for r in meta["resources"]] == ["idn_weather_daily.csv", "idn_weather_monthly.csv", "cities.csv"]


# ---------- exchange rates ----------

def fx_rates():
    return {
        "2026-10-08": {"USD": 1.10, "IDR": 17600.0, "SGD": 1.45, "JPY": 160.0},
        "2026-10-09": {"USD": 1.00, "IDR": 17000.0, "SGD": 1.40, "JPY": 170.0},
        "2026-11-02": {"USD": 1.20, "IDR": 18000.0, "SGD": 1.50, "JPY": 180.0},
    }


def test_idr_cross_rates():
    ecb = fx.rates_to_frame(fx_rates())
    ecb["date"] = pd.to_datetime(ecb["date"])
    wide = fx.idr_wide(ecb).set_index("date")
    assert wide.loc["2026-10-08", "idr_per_usd"] == pytest.approx(16000.0)
    assert wide.loc["2026-10-08", "idr_per_eur"] == 17600.0
    assert pd.isna(wide.loc["2026-10-08", "idr_per_gbp"])  # not in the payload
    monthly = fx.idr_monthly(wide.reset_index()).set_index(["month", "currency"])
    usd_oct = monthly.loc[(pd.Timestamp("2026-10-01"), "USD")]
    assert usd_oct["idr_per_unit_mean"] == pytest.approx(16500.0) and usd_oct["trading_days"] == 2


def test_fetch_rates_requests_one_year_at_a_time_and_falls_back_to_second_host():
    urls = []

    def get(url, params=None, timeout=None):
        urls.append(url)
        if "frankfurter.dev" in url:
            raise requests.exceptions.ConnectionError("down")
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"rates": {url[-10:]: {"IDR": 1.0}}})

    rates = fx.fetch_rates(SimpleNamespace(get=get), D("2024-06-01"), D("2026-02-01"))
    app_urls = [u for u in urls if "frankfurter.app" in u]
    assert app_urls == [
        "https://api.frankfurter.app/2024-06-01..2024-12-31",
        "https://api.frankfurter.app/2025-01-01..2025-12-31",
        "https://api.frankfurter.app/2026-01-01..2026-02-01",
    ]
    assert len(rates) == 3


def test_fx_build(tmp_path):
    big = {f"2026-{m:02d}-{d:02d}": {"IDR": 17000.0 + d, "USD": 1.1, "SGD": 1.4, **{f"X{i}": 1.0 for i in range(2000)}}
           for m in range(1, 13) for d in range(1, 29)}
    fetchers = {"ecb_reference_rates": lambda prev: fx.rates_to_frame(big)}
    report = pipeline.build(fx.SPEC, tmp_path / "v1", None, pd.Timestamp("2026-12-31"), "u/s", fetchers=fetchers)
    assert not report.failed
    wide = pd.read_csv(tmp_path / "v1" / "idr_exchange_rates.csv")
    assert len(wide) == 12 * 28 and list(wide.columns)[:3] == ["date", "idr_per_eur", "idr_per_usd"]
