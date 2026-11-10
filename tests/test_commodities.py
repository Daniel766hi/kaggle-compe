"""Offline tests for the commodity prices dataset, with a small workbook shaped like the World Bank Pink Sheet."""

import dataclasses
import io
import json

import pandas as pd

from kaggle_pipeline import pipeline
from kaggle_pipeline.datasets import commodities as cm

SERIES = [("Crude oil, Brent", "($/bbl)"), ("Coal, Australian", "($/mt)"), ("Palm oil", "($/mt)"),
          ("Rice, Thai 5% ", "($/mt)"), ("Rubber, TSR20 **", "($/kg)"), ("Nickel", "($/mt)"),
          ("Natural gas index", "(2010=100)"), ("Gold", "($/troy oz)")]
INDEX_HEADER = [  # four indented header rows, as in the real sheet
    ["Total Index", None, None, None], ["Energy", None, None, None], ["Non-energy **", None, None, " "],
    [None, "Agriculture **", None, " "], [None, None, "Beverages", None], [None, None, "Food **", " "],
    [None, None, None, "Oils & Meals"], [None, None, None, "Grains"], [None, None, None, "Other Food **"],
    [None, None, "Raw Materials", " "], [None, None, None, "Timber"], [None, None, None, "Other Raw Mat."],
    [None, "Fertilizers **", None, " "], [None, "Metals  & Minerals", None, None],
    [None, None, "Base Metals (ex. iron ore)", None], ["Precious Metals", None, None, " "],
]


def workbook(n_months=150):
    months = [f"{d.year}M{d.month:02d}" for d in pd.date_range("2014-01-01", periods=n_months, freq="MS")]
    title = [["World Bank Commodity Price Data (The Pink Sheet)"], ["monthly prices"], ["(nominal)"], ["Updated on November 03, 2026"]]
    prices = title + [[None] + [n for n, _ in SERIES], [None] + [u for _, u in SERIES]]
    for i, m in enumerate(months):
        row = [m]
        for j, (name, _) in enumerate(SERIES):
            if name.startswith("Rubber") and i < 24:
                row.append("…")  # a series that starts later
            elif name == "Nickel" and i == 100:
                row.append("..")  # a missing month in the middle
            else:
                row.append(100.0 + j * 10 + i)
        prices.append(row)
    indices = title + [[None]] + [[None] + [h[k] for h in INDEX_HEADER] for k in range(4)]
    indices += [[m] + [50.0 + i + k for k in range(16)] for i, m in enumerate(months)]
    buf = io.BytesIO()
    with pd.ExcelWriter(buf) as xl:
        pd.DataFrame(prices).to_excel(xl, sheet_name="Monthly Prices", header=False, index=False)
        pd.DataFrame(indices).to_excel(xl, sheet_name="Monthly Indices", header=False, index=False)
    return buf.getvalue()


class Resp:
    def __init__(self, code, content=b"", text=""):
        self.status_code, self.content, self.text = code, content, text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    def __init__(self, page_ok=True):
        self.page_ok, self.calls = page_ok, []

    def get(self, url, timeout=None):
        self.calls.append(url)
        if url == cm.PAGE:
            if not self.page_ok:
                return Resp(503)
            return Resp(200, text='<a href="https://thedocs.worldbank.org/en/doc/abc-0050012027/related/'
                                  'CMO-Historical-Data-Monthly.xlsx">Monthly prices</a>')
        return Resp(200, workbook())


def test_the_current_link_is_read_from_the_page_with_a_fallback():
    assert cm.workbook_url(FakeSession()).endswith("abc-0050012027/related/CMO-Historical-Data-Monthly.xlsx")
    assert cm.workbook_url(FakeSession(page_ok=False)) == cm.FALLBACK


def test_ids_groups_and_units():
    assert cm.commodity_id("Rice, Thai 5% ") == "rice_thai_5pct"
    assert cm.commodity_id("Rubber, TSR20 **") == "rubber_tsr20"
    assert cm.commodity_id("Rice, Viet Namese 5%") == "rice_vietnamese_5pct"
    assert cm.group_of("Palm kernel oil") == "oils_meals" and cm.group_of("Iron ore, cfr spot") == "base_metals"
    assert cm.group_of("Something new") == "other"


def test_prices_are_tidy_with_gaps_left_empty_and_changes_matched_on_months():
    df = cm.parse_prices(workbook())
    assert set(df["commodity_id"]) == {cm.commodity_id(n) for n, _ in SERIES}
    rubber = df[df["commodity_id"] == "rubber_tsr20"]
    assert rubber["month"].min() == pd.Timestamp("2016-01-01") and rubber["unit"].iloc[0] == "$/kg"
    nickel = df[df["commodity_id"] == "nickel"].set_index("month")
    gap = pd.Timestamp("2014-01-01") + pd.DateOffset(months=100)
    assert gap not in nickel.index
    after = nickel.loc[gap + pd.DateOffset(months=1)]
    assert pd.isna(after["mom_pct"])  # never computed across the missing month
    p = nickel.loc[pd.Timestamp("2016-01-01")]
    assert p["yoy_pct"] == round((p["price"] / nickel.loc[pd.Timestamp("2015-01-01"), "price"] - 1) * 100, 2)


def test_indices_are_named_from_the_indented_headers():
    ix = cm.parse_indices(workbook())
    assert list(ix.columns) == ["month"] + list(cm.INDEX_NAMES)
    assert ix["precious_metals"].iloc[0] == 65.0 and ix["total"].iloc[0] == 50.0


def test_summary_flags_indonesia_and_places_the_latest_price_in_its_10_year_range():
    s = cm.summarize(cm.parse_prices(workbook())).set_index("commodity_id")
    assert s.loc["palm_oil", "indonesia_major"] and not s.loc["gold", "indonesia_major"]
    palm = s.loc["palm_oil"]  # rises every month, so the latest month is the 10-year high
    assert palm["percentile_10y"] == round(100 * 119 / 120, 1) and palm["all_time_high_month"] == palm["last_month"]
    assert palm["change_12m_pct"] == round((palm["latest_price"] / (palm["latest_price"] - 12) - 1) * 100, 2)


def test_full_build_writes_every_file_and_the_movers_skip_the_index_series(tmp_path, monkeypatch):
    monkeypatch.setattr(cm, "make_session", lambda: FakeSession())
    spec = dataclasses.replace(cm.SPEC, tables=[dataclasses.replace(t, min_rows=1) for t in cm.TABLES])
    report = pipeline.build(spec, tmp_path / "v1", None, pd.Timestamp("2026-11-10"), "u/s")
    assert not report.failed, report.failed
    meta = json.loads((tmp_path / "v1" / "dataset-metadata.json").read_text())
    assert [r["path"] for r in meta["resources"]] == [t.file_name for t in cm.TABLES]
    for resource in meta["resources"]:
        assert all(f["description"] for f in resource["schema"]["fields"]), resource["path"]
    movers = meta["description"].split("## Latest movements")[1].split("Indonesia's key commodities")[0]
    assert "Natural gas index" not in movers and "Palm oil" in meta["description"]


def test_monthly_datasets_skip_scheduled_runs_on_other_days(monkeypatch):
    from kaggle_pipeline import __main__ as main
    monkeypatch.setenv("GITHUB_EVENT_NAME", "schedule")

    monkeypatch.setattr(main, "datetime", type("D", (), {"now": staticmethod(lambda tz=None: pd.Timestamp("2026-11-10", tz="UTC"))}))
    assert main.main(["commodities"]) == 0  # the 10th is not a run day: skipped before any download
