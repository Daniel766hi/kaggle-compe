"""Offline tests for the airports (OurAirports) and policy rates (BIS) datasets."""

import dataclasses
import io
import json
import zipfile

import pandas as pd

from kaggle_pipeline import pipeline
from kaggle_pipeline.datasets import airports as ap
from kaggle_pipeline.datasets import policy_rates as pr


class Resp:
    def __init__(self, content=b"", status=200):
        self.content, self.status_code = content, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def build_ok(module, session, tmp_path, monkeypatch):
    monkeypatch.setattr(module, "make_session", lambda: session)
    spec = dataclasses.replace(module.SPEC, tables=[dataclasses.replace(t, min_rows=1) for t in module.TABLES])
    report = pipeline.build(spec, tmp_path / "v1", None, pd.Timestamp("2026-11-27"), "u/s")
    assert not report.failed, report.failed
    meta = json.loads((tmp_path / "v1" / "dataset-metadata.json").read_text())
    for resource in meta["resources"]:
        assert all(f["description"] for f in resource["schema"]["fields"]), resource["path"]
    return meta


# ---------- airports ----------

AIRPORTS = """id,ident,type,name,latitude_deg,longitude_deg,elevation_ft,continent,iso_country,iso_region,municipality,scheduled_service,icao_code,iata_code
26835,WIII,large_airport,Soekarno-Hatta International Airport,-6.12557,106.655998,34,AS,ID,ID-BT,Jakarta,yes,WIII,CGK
26836,WADD,large_airport,I Gusti Ngurah Rai Airport,-8.748,115.167,14,AS,ID,ID-BA,Denpasar,yes,WADD,DPS
9,XX01,small_airport,Strip,-7.0,110.0,,AS,ID,ID-JT,,no,,
10,XX02,closed,Old Field,-7.1,110.1,100,AS,ID,ID-JT,,no,,
11,NA01,heliport,Pad,0,0,0,NA,NA,NA-KH,,no,,
"""
RUNWAYS = """id,airport_ref,airport_ident,length_ft,width_ft,surface,lighted,closed,le_ident,he_ident
1,26835,WIII,12008,197,ASP,1,0,07R,25L
2,26836,WADD,9842,148,CONC,1,0,09,27
3,9,XX01,2000,60,GRS,0,0,18,36
4,10,XX02,13000,100,ASP,0,1,01,19
"""
COUNTRIES = "code,name\nID,Indonesia\nNA,Namibia\n"
REGIONS = "code,name\nID-BT,Banten\nID-BA,Bali\nID-JT,Jawa Tengah\nNA-KH,Khomas\n"


class OASession:
    def get(self, url, timeout=None):
        body = {"airports": AIRPORTS, "runways": RUNWAYS, "countries": COUNTRIES, "regions": REGIONS}[url.rsplit("/", 1)[1][:-4]]
        return Resp(body.encode())


def test_airports_join_names_convert_units_and_keep_namibia(tmp_path, monkeypatch):
    read = lambda s: pd.read_csv(io.StringIO(s), keep_default_na=False, na_values=[""])
    a = ap.tidy_airports(read(AIRPORTS), read(COUNTRIES), read(REGIONS)).set_index("iata_code", drop=False)
    assert a.loc["CGK", "region"] == "Banten" and a.loc["CGK", "elevation_m"] == round(34 * 0.3048, 1)
    assert a.set_index("airport_id").loc[11, "country_code"] == "NA"  # Namibia's code is not read as missing
    r = ap.tidy_runways(read(RUNWAYS)).set_index("runway_id")
    assert r.loc[2, "paved"] and not r.loc[3, "paved"] and r.loc[1, "ends"] == "07R/25L" and r.loc[1, "length_m"] == 3660
    c = ap.countries(ap.tidy_airports(read(AIRPORTS), read(COUNTRIES), read(REGIONS)), ap.tidy_runways(read(RUNWAYS)))
    idn = c.set_index("country_code").loc["ID"]
    assert idn["scheduled_airports"] == 2 and idn["large_airports"] == 2 and idn["longest_runway_m"] == 3660  # closed runway ignored
    assert idn["paved_runway_share_pct"] == round(200 / 3, 1)
    build_ok(ap, OASession(), tmp_path, monkeypatch)


# ---------- policy rates ----------

def bis_zip():
    rows = []
    def add(freq, area, period, value, status="A: Normal value", breaks=""):
        rows.append({"FREQ:Frequency": freq, "REF_AREA:Reference area": area, "TIME_PERIOD:Time period or range": period,
                     "OBS_VALUE:Observation Value": value, "TITLE:Title": "Central bank policy rates",
                     "SUPP_INFO_BREAKS:Supplemental information and breaks": breaks, "OBS_STATUS:Observation Status": status})
    note = "The rate shift from 6.5% to 5.25% on 19 Aug 2016 does not represent a cut."
    for day, v in (("2016-08-18", "6.5"), ("2016-08-19", "5.25"), ("2025-11-01", "4.75"), ("2026-05-20", "5.25"),
                   ("2026-11-18", "6"), ("2026-11-20", "6")):
        add("D: Daily", "ID: Indonesia", day, v, breaks=note)
    add("D: Daily", "ID: Indonesia", "2026-11-21", "", status="M: Missing value; data cannot exist")
    for month, v in (("2016-08", "5.25"), ("2026-10", "5.75")):
        add("M: Monthly", "ID: Indonesia", month, v, breaks=note)
    add("D: Daily", "US: United States", "2026-11-20", "3.875")
    add("M: Monthly", "US: United States", "2026-10", "3.875")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("WS_CBPOL_csv_flat.csv", pd.DataFrame(rows).to_csv(index=False))
    return buf.getvalue()


class BISSession:
    def get(self, url, timeout=None):
        return Resp(bis_zip())


def test_policy_rates_moves_breaks_and_latest(tmp_path, monkeypatch):
    d, m, c = pr.tidy(pr.download(BISSession()))
    assert len(d[d["country_code"] == "ID"]) == 6  # the missing-value row is dropped
    assert m["month"].min() == pd.Timestamp("2016-08-01") and set(c["country_code"]) == {"ID", "US"}
    mv = pr.changes(d, c).set_index("date")
    assert mv.loc["2016-08-19", "possible_break"] and mv.loc["2016-08-19", "change_bp"] == -125.0
    assert not mv.loc["2026-11-18", "possible_break"] and mv.loc["2026-11-18", "direction"] == "hike"
    lt = pr.latest(d, pr.changes(d, c)).set_index("country_code").loc["ID"]
    assert lt["rate_pct"] == 6.0 and lt["last_move_bp"] == 75.0 and lt["change_12m_bp"] == 125.0
    assert lt["peak_since_2022_pct"] == 6.0 and lt["from_peak_bp"] == 0.0
    assert pr.note_dates("from 9 Aug 2001; in Feb 2008 it changed") == ({pd.Timestamp("2001-08-09")}, {(2008, 2)})
    build_ok(pr, BISSession(), tmp_path, monkeypatch)
