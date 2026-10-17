"""Offline tests for the Indonesian politics dataset, with synthetic GDELT files and Wikidata rows."""

import io
import zipfile
from datetime import date

import pandas as pd
import pytest

from kaggle_pipeline import pipeline
from kaggle_pipeline.datasets import idn_politics as ip

def gdelt_row(event_id, columns, country="ID", root="1", event="141", quad="3", geo="Jakarta, Jakarta Raya, Indonesia",
              geo_type="4", day="20261015", articles="4", tone="-3.5"):
    row = dict.fromkeys(columns, "")
    row.update({
        "GLOBALEVENTID": str(event_id), "SQLDATE": day, "Actor1Name": "PROTESTER", "Actor1Type1Code": "CVL",
        "Actor2Name": "INDONESIA", "Actor2CountryCode": "IDN", "Actor2Type1Code": "GOV", "IsRootEvent": root,
        "EventCode": event, "EventBaseCode": event[:3], "EventRootCode": event[:2], "QuadClass": quad,
        "GoldsteinScale": "-6.5", "NumMentions": "8", "NumSources": "2", "NumArticles": articles, "AvgTone": tone,
        "ActionGeo_Type": geo_type, "ActionGeo_FullName": geo, "ActionGeo_CountryCode": country,
        "ActionGeo_ADM1Code": "ID04", "ActionGeo_Lat": "-6.2", "ActionGeo_Long": "106.8",
        "DATEADDED": day + ("000000" if len(columns) == 61 else ""), "SOURCEURL": f"https://news.example/{event_id}",
    })
    return "\t".join(row[c] for c in columns)


def zipped(lines):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("export.CSV", "\n".join(lines) + "\n")
    return buf.getvalue()


@pytest.mark.parametrize("columns", [ip.GDELT1_COLUMNS, ip.GDELT2_COLUMNS])
def test_read_export_keeps_root_events_located_in_indonesia(columns):
    content = zipped([
        gdelt_row(1, columns),
        gdelt_row(2, columns, root="0"),                                # not a root event
        gdelt_row(3, columns, country="MY", geo="Kuala Lumpur, Malaysia"),  # elsewhere
        gdelt_row(4, columns, event="0233", quad="2"),
    ])
    raw = ip.read_export(content)
    assert sorted(raw["GLOBALEVENTID"]) == ["1", "4"]


def test_tidy_events_labels_codes_and_finds_the_province():
    raw = ip.read_export(zipped([
        gdelt_row(1, ip.GDELT1_COLUMNS),
        gdelt_row(2, ip.GDELT1_COLUMNS, geo="Indonesia", geo_type="1"),  # national: no province
    ]))
    out = ip.tidy_events(raw, {"141": "Demonstrate or rally"}, {"GOV": "Government", "CVL": "Civilian"})
    first = out.iloc[0]
    assert first["event"] == "Demonstrate or rally" and first["event_root"] == "Protest"
    assert first["quad_class"] == "verbal conflict"
    assert (first["actor1_type"], first["actor2_type"]) == ("Civilian", "Government")
    assert first["province"] == "Jakarta Raya" and first["date"] == pd.Timestamp("2026-10-15")
    assert pd.isna(out.iloc[1]["province"])


def test_plan_refreshes_recent_days_then_backfills_newest_first():
    previous = pd.DataFrame({"date_added": pd.to_datetime(["2024-10-21", "2024-10-23"])})
    recent, older = ip.plan_days(previous, date(2024, 10, 26), first_day=date(2024, 10, 20), recent_days=2)
    assert recent == [date(2024, 10, 26), date(2024, 10, 25)]
    assert older == [date(2024, 10, 24), date(2024, 10, 22), date(2024, 10, 20)]


def test_fetch_events_stops_backfilling_when_the_budget_is_spent(monkeypatch):
    calls = []

    def fake_day(session, day):
        calls.append(day)
        return ip.read_export(zipped([gdelt_row(len(calls), ip.GDELT1_COLUMNS, day=f"{day:%Y%m%d}")]))
    monkeypatch.setattr(ip, "fetch_day", fake_day)
    monkeypatch.setattr(ip, "lookup", lambda session, url: {})
    ticks = iter(range(0, 10_000, 100))
    events = ip.fetch_events(None, None, date(2026, 10, 16), budget_s=150, clock=lambda: next(ticks))
    assert len(calls) < 100  # stopped long before backfilling all ~730 days
    assert events["date_added"].max() == pd.Timestamp("2026-10-16")


def test_fetch_events_fails_only_if_nothing_downloads(monkeypatch):
    def broken(session, day):
        raise FileNotFoundError("not published")
    monkeypatch.setattr(ip, "fetch_day", broken)
    monkeypatch.setattr(ip, "lookup", lambda session, url: {})
    with pytest.raises(RuntimeError, match="no GDELT data"):
        ip.fetch_events(None, None, date(2024, 10, 22), budget_s=0)


WIKI_HTML = """
<h2>Ministers</h2>
<table class="wikitable">
<tr><th>Portfolio</th><th>Minister</th><th>Took office</th><th>Left office</th><th colspan="2">Party</th></tr>
<tr><td rowspan="2">Minister of Finance</td><td>Sri Mulyani Indrawati[a]</td><td>21 October 2024</td><td>8 September 2025</td><td></td><td>Independent</td></tr>
<tr><td>Purbaya Yudhi Sadewa</td><td>8 September 2025</td><td>Incumbent</td><td></td><td>Independent</td></tr>
<tr><td rowspan="2">Minister of Cooperatives</td><td>Budi Arie Setiadi</td><td>21 October 2024[1]</td><td>8 September 2025</td><td></td><td>Gerindra</td></tr>
<tr><td>Ferry Juliantono</td><td>8 September 2025</td><td>Incumbent</td><td></td><td>Gerindra</td></tr>
<tr><td>Minister of Hajj</td><td>New Person</td><td>8 September 2025</td><td>Incumbent</td><td></td><td></td></tr>
</table>
<table class="wikitable"><tr><th>Event</th><th>Date</th></tr><tr><td>Inauguration</td><td>21 October 2024</td></tr></table>
"""


def test_parse_cabinet_tables_handles_merged_cells_footnotes_and_incumbents():
    df = ip.parse_cabinet_tables(WIKI_HTML).set_index("person")
    assert len(df) == 5
    assert df.loc["Purbaya Yudhi Sadewa", "position"] == "Minister of Finance"  # from the merged cell
    assert df.loc["Sri Mulyani Indrawati", "end_date"] == pd.Timestamp("2025-09-08")  # footnote removed
    assert pd.isna(df.loc["Ferry Juliantono", "end_date"])  # "Incumbent"
    assert df.loc["Budi Arie Setiadi", "start_date"] == pd.Timestamp("2024-10-21")
    assert df.loc["Ferry Juliantono", "party"] == "Gerindra"
    assert df.loc["Ferry Juliantono", "level"] == "minister"  # the filled one of the two party columns


def test_parse_cabinet_tables_fails_loudly_when_the_article_changes_shape():
    with pytest.raises(RuntimeError, match="no cabinet table"):
        ip.parse_cabinet_tables("<table><tr><th>Event</th></tr><tr><td>x</td></tr></table>")


def test_cabinet_changes_find_reshuffles_and_previous_holders():
    changes = ip.cabinet_changes(ip.parse_cabinet_tables(WIKI_HTML)).set_index("person")
    assert changes.loc["Purbaya Yudhi Sadewa", "previous_holder"] == "Sri Mulyani Indrawati"
    assert changes.loc["Ferry Juliantono", "previous_holder"] == "Budi Arie Setiadi"
    assert pd.isna(changes.loc["New Person", "previous_holder"])  # a new ministry
    assert set(changes["appointments_that_day"]) == {3}


def test_daily_tables_count_protests_and_weight_tone_by_articles():
    raw = ip.read_export(zipped([
        gdelt_row(1, ip.GDELT1_COLUMNS, articles="3", tone="-4"),
        gdelt_row(2, ip.GDELT1_COLUMNS, event="0233", quad="2", articles="1", tone="4"),
    ]))
    national, province = ip.daily_tables(ip.tidy_events(raw, {}, {}).astype({"avg_tone": float, "num_articles": float,
                                                                              "goldstein": float}))
    day = national.iloc[0]
    assert (day["events"], day["protests"], day["articles"]) == (2, 1, 4)
    assert day["avg_tone"] == pytest.approx(-2.0)  # (3 * -4 + 1 * 4) / 4
    assert province.iloc[0]["province"] == "Jakarta Raya"


def test_full_build_writes_every_file_with_column_descriptions(tmp_path):
    lines = [gdelt_row(i, ip.GDELT1_COLUMNS, day=f"202610{10 + i % 5}") for i in range(1, 81)]
    events = ip.tidy_events(ip.read_export(zipped(lines)), {}, {})
    cabinet = ip.parse_cabinet_tables(WIKI_HTML)
    cabinet = pd.concat([cabinet.assign(person=cabinet["person"] + str(i)) for i in range(10)])
    fetchers = {"events": lambda prev: events, "cabinet_positions": lambda prev: cabinet}
    report = pipeline.build(ip.SPEC, tmp_path / "v1", None, pd.Timestamp("2026-10-17"), "u/s", fetchers=fetchers)
    assert not report.failed, report.failed
    import json
    meta = json.loads((tmp_path / "v1" / "dataset-metadata.json").read_text())
    assert [r["path"] for r in meta["resources"]] == [t.file_name for t in ip.TABLES]
    for resource in meta["resources"]:
        assert all(field["description"] for field in resource["schema"]["fields"]), resource["path"]
    assert "80 events" in meta["description"]
    assert len(pd.read_csv(tmp_path / "v1" / "daily_national.csv")) == 5
