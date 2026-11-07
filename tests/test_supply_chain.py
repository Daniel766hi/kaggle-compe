"""Offline tests for the supply chain dataset, with PortWatch-shaped CSVs and a fake GSCPI workbook."""

import dataclasses
import io
import json

import pandas as pd

from kaggle_pipeline import pipeline
from kaggle_pipeline.datasets import supply_chain as sc

V = sc.VESSELS


def country_csv(days=400):
    rows = []
    for iso, name, base in (("IDN", "Indonesia", 200), ("WLD", "World", 4000), ("110", "Advanced Economies", 2000)):
        for i, day in enumerate(pd.date_range("2024-01-01", periods=days)):
            calls = {f"portcalls_{v}": base // 10 for v in V}
            calls.update(portcalls_cargo=base // 10 * 4, portcalls=base // 2)
            trade = {f"{f}_{v}": 1000.0 for f in ("import", "export") for v in V}
            trade.update({"import_cargo": 4000.0, "import": 5000.0 + i, "export_cargo": 4000.0, "export": 5000.0})
            rows.append({"ISO3": iso, "country": name, "date": f"{day:%Y/%m/%d}", **calls, **trade,
                         "shipment": 10000.0 + i, "portcalls_container_30MA": 20.0,
                         "portcalls_container_30MA_yoy_doy": 1.5, "shipment_30MA": 10000.0,
                         "shipment_30MA_yoy_doy": 2.0, "ObjectId": len(rows) + 1})
    return pd.DataFrame(rows).to_csv(index=False)


def choke_csv(days=400):
    rows = []
    for cid, name in (("chokepoint5", "Malacca Strait"), ("chokepoint4", "Bab el-Mandeb Strait")):
        for day in pd.date_range("2024-01-01", periods=days):
            n = 200 if cid == "chokepoint5" else (60 if day < pd.Timestamp("2025-01-01") else 30)
            rec = {"date": f"{day:%Y/%m/%d}", "year": day.year, "month": day.month, "day": day.day, "portid": cid,
                   "portname": name, **{f"n_{v}": n // 5 for v in V}, "n_cargo": n // 5 * 4, "n_total": n,
                   **{f"capacity_{v}": 1e5 for v in V}, "capacity_cargo": 4e5, "capacity": 5e5}
            rows.append({**rec, "ObjectId": len(rows) + 1})
    return pd.DataFrame(rows).to_csv(index=False)


def ports_csv(n=600):
    return pd.DataFrame([{
        "X": 106.9, "Y": -6.1, "portid": f"port{i}", "portname": "Tanjung Priok" if i == 0 else f"Port {i}",
        "country": "Indonesia", "ISO3": "IDN", "continent": "Asia & Pacific", "fullname": "x", "lat": -6.1, "lon": 106.9,
        "vessel_count_total": 9315 - i, "vessel_count_container": 1, "vessel_count_dry_bulk": 1,
        "vessel_count_general_cargo": 1, "vessel_count_RoRo": 1, "vessel_count_tanker": 1,
        "industry_top1": "Mineral Products", "industry_top2": "", "industry_top3": "",
        "share_country_maritime_import": 2.5, "share_country_maritime_export": 2.4, "LOCODE": "ID TPP",
        "pageid": "x", "countrynoaccents": "Indonesia", "ObjectId": i + 1} for i in range(n)]).to_csv(index=False)


def gscpi_xls():
    rows = [["Date", "GSCPI"], [None, None]] + [[f"{d:%d-%b-%Y}", 0.1 * i]
                                               for i, d in enumerate(pd.date_range("1998-01-31", periods=330, freq="ME"))]
    buf = io.BytesIO()
    pd.DataFrame(rows).to_excel(buf, header=False, index=False)  # xlsx here; read_excel handles both formats
    return buf.getvalue()


class Resp:
    def __init__(self, code, content):
        self.status_code, self.content, self.text = code, content, content[:200].decode("utf-8", "replace")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    def __init__(self, pending=0):
        self.pending, self.calls = pending, []

    def get(self, url, timeout=None):
        self.calls.append(url)
        if url == sc.GSCPI:
            return Resp(200, gscpi_xls())
        if self.pending:
            self.pending -= 1
            return Resp(202, b'{"message": "Up to date download file is being generated.", "progressInPercent": 40}')
        item = next(k for k, v in sc.ITEMS.items() if v in url)
        body = {"country_daily": country_csv, "chokepoint_daily": choke_csv, "ports": ports_csv}[item]()
        return Resp(200, ("﻿" + body).encode("utf-8"))


def test_download_waits_while_portwatch_regenerates_the_file():
    session, slept = FakeSession(pending=2), []
    df = sc.download_csv(session, sc.ITEMS["ports"], sleep=slept.append)
    assert len(df) == 600 and slept == [sc.WAIT_S, sc.WAIT_S] and "portid" in df.columns


def test_download_gives_up_after_the_wait_budget():
    session = FakeSession(pending=10)
    try:
        sc.download_csv(session, sc.ITEMS["ports"], rounds=3, sleep=lambda s: None)
    except RuntimeError as exc:
        assert "regenerated" in str(exc)
    else:
        raise AssertionError("expected a RuntimeError")


def test_tidy_tables_rename_and_flag_aggregates():
    country = sc.tidy_country(pd.read_csv(io.StringIO(country_csv(3))))
    flags = country.drop_duplicates("iso3").set_index("iso3")["is_aggregate"].to_dict()
    assert flags == {"IDN": False, "WLD": True, "110": True}
    assert country["date"].iloc[0] == pd.Timestamp("2024-01-01") and "shipment_30ma_yoy" in country
    choke = sc.tidy_chokepoints(pd.read_csv(io.StringIO(choke_csv(2))))
    assert {"chokepoint", "transits", "transits_tanker", "capacity"} <= set(choke.columns)


def test_monthly_tables_use_complete_months_and_year_on_year_change():
    choke = sc.tidy_chokepoints(pd.read_csv(io.StringIO(choke_csv(400))))  # 2024-01-01 to 2025-02-03
    monthly = sc.chokepoint_monthly(choke).set_index(["chokepoint", "month"])
    assert monthly.index.get_level_values("month").max() == pd.Timestamp("2025-01-01")  # February is incomplete
    red_sea = monthly.loc[("Bab el-Mandeb Strait", pd.Timestamp("2025-01-01"))]
    assert red_sea["transits_per_day"] == 30 and red_sea["transits_yoy_pct"] == -50.0


def test_gscpi_is_read_from_the_workbook():
    g = sc.fetch_gscpi(FakeSession())
    assert g["month"].iloc[0] == pd.Timestamp("1998-01-01") and len(g) == 330


def test_full_build_writes_every_file_with_column_descriptions(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "make_session", lambda: FakeSession())
    spec = dataclasses.replace(sc.SPEC, tables=[dataclasses.replace(t, min_rows=1) for t in sc.TABLES])
    report = pipeline.build(spec, tmp_path / "v1", None, pd.Timestamp("2026-11-07"), "u/s")
    assert not report.failed, report.failed
    meta = json.loads((tmp_path / "v1" / "dataset-metadata.json").read_text())
    assert [r["path"] for r in meta["resources"]] == [t.file_name for t in sc.TABLES]
    for resource in meta["resources"]:
        assert all(f["description"] for f in resource["schema"]["fields"]), resource["path"]
    assert "2 countries, plus world and regional aggregates" not in meta["description"]
    assert "1 countries, plus world and regional aggregates" in meta["description"]
