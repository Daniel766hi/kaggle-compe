"""Offline tests for the electricity, Indonesia solar, ASEAN macro, Indonesia retail and minerals datasets."""

import dataclasses
import json

import pandas as pd
import pytest

from kaggle_pipeline import pipeline
from kaggle_pipeline.datasets import electricity as el
from kaggle_pipeline.datasets import idn_retail as rt
from kaggle_pipeline.datasets import idn_solar as so
from kaggle_pipeline.datasets import macro_asean as ma
from kaggle_pipeline.datasets import minerals as mi


class Resp:
    def __init__(self, content=b"", status=200, payload=None):
        self.content, self.status_code, self._payload = content, status, payload
        self.text = content.decode("utf-8", "replace") if isinstance(content, bytes) else str(content)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def json(self):
        return self._payload if self._payload is not None else json.loads(self.content)


def build_ok(spec_module, session, tmp_path, monkeypatch, date="2026-11-23"):
    monkeypatch.setattr(spec_module, "make_session", lambda: session)
    spec = dataclasses.replace(spec_module.SPEC, tables=[dataclasses.replace(t, min_rows=1) for t in spec_module.TABLES])
    report = pipeline.build(spec, tmp_path / "v1", None, pd.Timestamp(date), "u/s")
    assert not report.failed, report.failed
    meta = json.loads((tmp_path / "v1" / "dataset-metadata.json").read_text())
    for resource in meta["resources"]:
        assert all(f["description"] for f in resource["schema"]["fields"]), resource["path"]
    return meta


# ---------- electricity (Ember) ----------

EMBER_COLS = ["Area", "ISO 3 code", "Area type", "Electricity source", "Is aggregated source", "Generation (TWh)",
              "Generation YoY change (%)", "Share of generation (%)", "Emissions (MtCO2e)", "Emissions intensity (gCO2e/kWh)",
              "Continent", "Ember region", "EU member", "OECD member", "G20 member", "G7 member", "ASEAN member"]


def ember_yearly():
    rows = []
    for year, coal in ((2020, 60.0), (2025, 70.0)):
        for src, share, agg in (("Coal", coal, False), ("Solar", 1.0, False), ("Clean", 100 - coal, True),
                                ("Total generation", 100.0, True)):
            rows.append(["Indonesia", "IDN", "Country or economy", src, agg, share * 5, 3.0, share, 10.0, 700.0,
                         "Asia", "Asia", False, False, True, False, True] + [year, None])
    rows.append(["ASEAN", None, "Region", "Total generation", True, 1000.0, 2.0, 100.0, 500.0, 500.0, "Asia", "Asia",
                 False, False, False, False, False, 2025, None])
    return pd.DataFrame(rows, columns=EMBER_COLS + ["Year", "Capacity (GW)"])


def test_electricity_tidies_and_summarizes(tmp_path, monkeypatch):
    raw = ember_yearly()
    y = el.tidy_yearly(raw)
    assert y.loc[y["source"] == "Coal", "intensity_gco2e_kwh"].isna().all()  # intensity kept on totals only
    s = el.summary(y, el.tidy_areas(raw)).set_index("area")
    assert list(s.index) == ["Indonesia"]  # regions are left out of the country summary
    idn = s.loc["Indonesia"]
    assert idn["coal_pct"] == 70.0 and idn["gas_pct"] == 0.0 and idn["clean_pct_change_5y"] == -10.0

    monthly = raw.rename(columns={"Year": "Date"}).assign(Date="2026-09-01")

    class Session:
        def get(self, url, timeout=None):
            return Resp((monthly if url == el.MONTHLY else raw).to_csv(index=False).encode())

    meta = build_ok(el, Session(), tmp_path, monkeypatch)
    assert "Indonesia (2025)" in meta["description"]


# ---------- Indonesia solar (NASA POWER) ----------

def power_payload(days=800):
    dates = pd.date_range("2023-01-01", periods=days).strftime("%Y%m%d")
    values = {p: {d: (5.0 if p == "ALLSKY_SFC_SW_DWN" else 1.0) for d in dates} for p in so.PARAMS}
    values["ALLSKY_SFC_SW_DWN"][dates[-1]] = -999.0  # not processed yet
    for p in values:
        values[p][dates[-1]] = -999.0
    return {"header": {"fill_value": -999.0}, "properties": {"parameter": values}}


def test_solar_fetch_derives_monthly_and_city_tables(tmp_path, monkeypatch):
    class Session:
        def get(self, url, params=None, timeout=None):
            return Resp(payload=power_payload())

    monkeypatch.setattr(so.time, "sleep", lambda s: None)
    monkeypatch.setattr(so, "CITIES", so.CITIES[:2])
    daily = so.fetch_all(Session(), pd.Timestamp("2026-11-23"), pause_s=0)
    assert len(daily) == 2 * 799  # the unprocessed last day is dropped
    m = so.monthly(daily)
    jan = m[(m["city"] == "Banda Aceh") & (m["month"] == pd.Timestamp("2023-01-01"))].iloc[0]
    assert jan["ghi_kwh_m2"] == 155.0 and jan["pv_kwh_per_kwp"] == 124.0  # 31 days x 5 kWh/m2, x 0.8
    c = so.cities(daily).set_index("city")
    assert c.loc["Medan", "pv_kwh_per_kwp_year"] == round(5.0 * 365.25 * 0.8, 1) and c.loc["Medan", "years"] == 2  # 2023 and 2024 are complete
    build_ok(so, Session(), tmp_path, monkeypatch)


# ---------- ASEAN macro (World Bank) ----------

class WBSession:
    def get(self, url, params=None, timeout=None):
        if "/indicator/" in url and "country/" in url:
            code = url.rsplit("/", 1)[1]
            if code == "SI.POV.GINI":
                return Resp(payload=[{"message": [{"key": "Invalid value"}]}])  # an indicator that fails
            data = [{"countryiso3code": iso, "country": {"id": iso[:2], "value": iso}, "date": str(y),
                     "value": float(y - 2000) if iso != "VNM" or y > 2015 else None}
                    for iso in ("IDN", "VNM", "WLD") for y in range(2010, 2026)]
            return Resp(payload=[{"page": 1}, data])
        if "/indicator/" in url:
            code = url.rsplit("/", 1)[1]
            return Resp(payload=[{"page": 1}, [{"name": f"Name of {code}", "sourceOrganization": "Org", "sourceNote": "Def"}]])
        return Resp(payload=[{"page": 1}, [
            {"id": "IDN", "name": "Indonesia", "region": {"value": "East Asia & Pacific"}, "incomeLevel": {"value": "Upper middle income"}},
            {"id": "WLD", "name": "World", "region": {"value": "Aggregates"}, "incomeLevel": {"value": "Aggregates"}}]])


def test_macro_panel_skips_failed_indicators_and_computes_change(tmp_path, monkeypatch):
    monkeypatch.setattr(ma.time, "sleep", lambda s: None)
    v = ma.fetch_values(WBSession(), pd.Timestamp("2026-11-23"))
    assert "SI.POV.GINI" not in set(v["indicator"]) and v["value"].notna().all()
    lt = ma.latest(v).set_index(["iso3", "indicator"])
    assert lt.loc[("IDN", "FR.INR.LEND"), "change_10y"] == 10.0
    assert pd.isna(lt.loc[("VNM", "FR.INR.LEND"), "value_10y_before"])  # no 2015 value for Vietnam
    c = ma.fetch_countries(WBSession()).set_index("iso3")
    assert c.loc["WLD", "is_aggregate"] and c.loc["IDN", "asean"] and c.loc["IDN", "g20"] and pd.isna(c.loc["WLD", "region"])
    build_ok(ma, WBSession(), tmp_path, monkeypatch)


# ---------- Indonesia retail (OpenStreetMap) ----------

def overpass_elements(iso):
    if iso != "ID-JK":
        return [{"type": "node", "id": 9, "lat": -6.3, "lon": 106.9, "tags": {"shop": "convenience", "name": "Warung"}}]
    return [
        {"type": "node", "id": 1, "lat": -6.2, "lon": 106.8, "tags": {"shop": "convenience", "brand": "Indomaret", "name": "Indomaret Sudirman"}},
        {"type": "node", "id": 2, "lat": -6.21, "lon": 106.81, "tags": {"shop": "convenience", "name": "ALFAMART KUNINGAN"}},
        {"type": "way", "id": 3, "center": {"lat": -6.22, "lon": 106.82}, "tags": {"shop": "supermarket", "name": "Super Indo"}},
        {"type": "node", "id": 4, "lat": -6.23, "lon": 106.83, "tags": {"shop": "convenience", "name": "Indomaret Fresh Kemang"}},
        {"type": "node", "id": 9, "lat": -6.3, "lon": 106.9, "tags": {"shop": "convenience", "name": "Warung"}},  # on the border
    ]


class OverpassSession:
    def __init__(self, busy=0):
        self.busy = busy

    def post(self, url, data=None, timeout=None, headers=None):
        if self.busy:
            self.busy -= 1
            return Resp(b"busy", status=429)
        iso = data["data"].split('"ISO3166-2"="')[1].split('"')[0]
        return Resp(payload={"elements": overpass_elements(iso)})


def test_retail_matches_chains_dedups_borders_and_summarizes(tmp_path, monkeypatch):
    monkeypatch.setattr(rt.time, "sleep", lambda s: None)
    stores = rt.fetch_stores(OverpassSession(busy=1), pause_s=0, sleep=lambda s: None)
    assert stores["osm_id"].is_unique  # the border store is kept once
    jk = stores[stores["province"] == "DKI Jakarta"].set_index("osm_id")
    assert jk.loc[2, "chain"] == "Alfamart" and jk.loc[3, "chain"] == "Superindo" and jk.loc[4, "chain"] == "Indomaret Fresh"
    s = rt.province_summary(stores).set_index("province").loc["DKI Jakarta"]
    assert (s["indomaret"], s["alfamart"], s["other_chains"], s["indomaret_vs_alfamart"]) == (2, 1, 1, 2.0)
    counts = rt.counts(stores, "2026-11-23")
    assert counts["stores"].sum() == len(stores)
    monkeypatch.setattr(rt, "fetch_stores", lambda session: stores)
    build_ok(rt, OverpassSession(), tmp_path, monkeypatch)


# ---------- minerals (USGS) ----------

def mcs_csv():
    header = ["MCS chapter", "Section", "Commodity", "Country", "Statistics", "Statistics_detail", "Unit", "Year", "Value",
              "Notes", "Is critical mineral 2025", "Other notes"]
    r = lambda c, s, d, y, v, n="": ["NICKEL", "World Mine Production and Reserves", "Nickel", c, s, d, "metric tons", y, v, n, "Yes", ""]
    rows = [r("Indonesia", "Production", "Mine production", "2025", "2,600,000", "Estimated."),
            r("Philippines", "Production", "Mine production", "2025", "330,000"),
            r("Brazil", "Production", "Mine production", "2025", "—"),
            r("Canada", "Production", "Mine production", "2025", "W"),
            r("World total", "Production", "Mine production: rounded", "2025", "3,900,000"),
            r("Indonesia", "Reserves", "Reserves", "2025", "Large"),
            ["NICKEL", "Salient Statistics—United States", "Nickel", "United States", "Price", "Price", "dollars", "2025", "15,000", "", "Yes", ""]]
    return pd.DataFrame(rows, columns=header).to_csv(index=False).encode("cp1252")


class MCSSession:
    def get(self, url, params=None, timeout=None):
        if url.endswith("/items"):
            return Resp(payload={"items": [{"id": "old", "title": "Mineral Commodity Summaries 2025 Data Release"},
                                           {"id": "new", "title": "Mineral Commodity Summaries 2026 Data Release"},
                                           {"id": "x", "title": "Something else"}]})
        if "/item/" in url:
            return Resp(payload={"files": [{"name": "MCS2026_Fig1.csv", "url": "f1"}, {"name": "MCS2026_Commodities_Data.csv", "url": "data"}]})
        return Resp(mcs_csv())


def test_minerals_parse_codes_and_leaders(tmp_path, monkeypatch):
    assert mi.latest_item(MCSSession()) == (2026, "new")
    ed, content = mi.download(MCSSession())
    p = mi.parse(content, ed)
    assert set(p["section"]) == {"World Mine Production and Reserves"}  # US salient rows are left out
    v = p.set_index(["country", "statistic"])["value"]
    assert v[("Brazil", "Production")] == 0.0 and pd.isna(v[("Canada", "Production")]) and pd.isna(v[("Indonesia", "Reserves")])
    assert p.set_index(["country", "statistic"]).loc[("Indonesia", "Production"), "is_estimate"]
    lead = mi.leaders(p).set_index("detail").loc["Mine production"]
    assert lead["top_country"] == "Indonesia" and lead["indonesia_rank"] == 1 and lead["indonesia_share_pct"] == pytest.approx(66.7)
    build_ok(mi, MCSSession(), tmp_path, monkeypatch)
