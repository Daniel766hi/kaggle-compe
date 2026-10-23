import json
import re
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
import requests

from kaggle_pipeline import kaggle_sync, pipeline
from kaggle_pipeline.datasets import DATASETS
from kaggle_pipeline.schema import KNOWN_KAGGLE_TAGS
from kaggle_pipeline.datasets.defi import SPEC, transform

from . import defi_fakes as fakes

REF = "someone/defi-daily-tvl-stablecoins-dex-yields"
DAY1, DAY2 = pd.Timestamp("2026-10-09"), pd.Timestamp("2026-10-10")


def fetchers(snapshot_date, broken=()):
    def fail(prev=None):
        raise requests.exceptions.ConnectionError("boom")

    f = {
        "defi_tvl_history": lambda prev: transform.defi_tvl_history(fakes.tvl_series()),
        "chain_tvl_history": lambda prev: transform.chain_tvl_history({"A": fakes.tvl_series()}),
        "stablecoin_supply_history": lambda prev: transform.stablecoin_supply_history(fakes.stablecoin_chart()),
        "dex_fees_history": lambda prev: transform.dex_fees_history(fakes.overview(), fakes.overview()),
        "protocols_snapshots": lambda prev: transform.protocols_snapshot(fakes.protocols(), snapshot_date),
        "chains_snapshots": lambda prev: transform.chains_snapshot(fakes.chains(), snapshot_date),
        "stablecoins_snapshots": lambda prev: transform.stablecoins_snapshot(fakes.stablecoins(), snapshot_date),
        "yield_pools_snapshots": lambda prev: transform.yield_pools_snapshot(fakes.yield_pools(), snapshot_date),
    }
    return {name: (fail if name in broken else fn) for name, fn in f.items()}


def run(out, previous, day, broken=()):
    return pipeline.build(SPEC, out, previous, day, REF, fetchers=fetchers(day, broken))


def test_first_run_writes_files_and_valid_metadata(tmp_path):
    out = tmp_path / "v1"
    report = run(out, None, DAY1)
    assert not report.failed
    meta = json.loads((out / "dataset-metadata.json").read_text())
    assert meta["id"] == REF
    assert 6 <= len(meta["title"]) <= 50
    assert 20 <= len(meta["subtitle"]) <= 80
    paths = [r["path"] for r in meta["resources"]]
    assert len(paths) == len(set(paths)) == 12  # 4 history CSVs + 4 panels + 4 latest CSVs
    for p in paths:
        assert (out / p).is_file()
    assert "protocols_latest.csv" in paths


def test_second_run_appends_snapshot_day_and_rerun_is_idempotent(tmp_path):
    run(tmp_path / "v1", None, DAY1)
    run(tmp_path / "v2", tmp_path / "v1", DAY2)
    panel = pd.read_parquet(tmp_path / "v2" / "protocols_snapshots.parquet")
    assert sorted(panel["snapshot_date"].unique()) == [DAY1, DAY2]
    latest = pd.read_csv(tmp_path / "v2" / "protocols_latest.csv")
    assert set(latest["snapshot_date"]) == {"2026-10-10"}

    run(tmp_path / "v3", tmp_path / "v2", DAY2)  # same day again
    again = pd.read_parquet(tmp_path / "v3" / "protocols_snapshots.parquet")
    assert len(again) == len(panel)


def test_failed_source_carries_previous_file_forward(tmp_path):
    run(tmp_path / "v1", None, DAY1)
    report = run(tmp_path / "v2", tmp_path / "v1", DAY2, broken={"yield_pools_snapshots", "defi_tvl_history"})
    assert set(report.carried_forward) == {"yield_pools_snapshots", "defi_tvl_history"}
    assert "unchanged (source error)" in report.version_notes(DAY2)
    pools = pd.read_parquet(tmp_path / "v2" / "yield_pools_snapshots.parquet")
    assert pools["snapshot_date"].unique().tolist() == [DAY1]
    assert (tmp_path / "v2" / "defi_tvl_history.csv").read_text() == (
        tmp_path / "v1" / "defi_tvl_history.csv"
    ).read_text()


def test_suspiciously_small_response_is_rejected(tmp_path):
    f = fetchers(DAY1)
    f["protocols_snapshots"] = lambda prev: transform.protocols_snapshot(fakes.protocols(3), DAY1)
    report = pipeline.build(SPEC, tmp_path / "v1", None, DAY1, REF, fetchers=f)
    assert "only 3 rows" in report.failed["protocols_snapshots"]
    assert not (tmp_path / "v1" / "protocols_snapshots.parquet").exists()


def test_shorter_history_than_before_is_rejected(tmp_path):
    run(tmp_path / "v1", None, DAY1)
    f = fetchers(DAY2)
    f["defi_tvl_history"] = lambda prev: transform.defi_tvl_history(fakes.tvl_series(1100))
    report = pipeline.build(SPEC, tmp_path / "v2", tmp_path / "v1", DAY2, REF, fetchers=f)
    assert "would shrink" in report.failed["defi_tvl_history"]
    assert len(pd.read_csv(tmp_path / "v2" / "defi_tvl_history.csv")) == 1200


def test_everything_failing_aborts(tmp_path):
    with pytest.raises(RuntimeError, match="Every source failed"):
        run(tmp_path / "v1", None, DAY1, broken=set(fetchers(DAY1)))


def scheduled_datasets():
    workflow = (Path(__file__).parent.parent / ".github" / "workflows" / "update-dataset.yml").read_text()
    # matrix: dataset: ${{ fromJSON(inputs.dataset && ... || '["defi", ...]') }}
    scheduled = re.search(r"\|\| '(\[.*?\])'", workflow).group(1)
    return json.loads(scheduled)


def test_scheduled_datasets_exist():
    assert set(scheduled_datasets()) <= set(DATASETS)


@pytest.mark.parametrize("spec", DATASETS.values(), ids=list(DATASETS))
def test_every_dataset_fits_kaggle_limits(spec):
    assert 6 <= len(spec.title) <= 50
    assert 20 <= len(spec.subtitle) <= 80
    assert 6 <= len(spec.slug) <= 50
    if spec.name in scheduled_datasets():
        assert spec.cover is not None and spec.cover.exists(), f"missing cover image {spec.cover}"
    names = [t.name for t in spec.tables]
    assert len(names) == len(set(names))
    assert set(spec.keywords) <= KNOWN_KAGGLE_TAGS, set(spec.keywords) - KNOWN_KAGGLE_TAGS
    assert len(spec.keywords) <= 5  # Kaggle: "You have exceeded the max category limit" at 6
    too_long = [c.name for t in spec.tables for c in t.columns if len(c.description) > 100]
    assert not too_long, f"column descriptions over 100 characters: {too_long}"


class FakeApi:
    def __init__(self, status_error=None):
        self.status_error = status_error
        self.calls = []

    def dataset_status(self, ref):
        if self.status_error:
            raise self.status_error
        return "ready"

    def dataset_create_version(self, folder, notes, **kw):
        self.sent_meta = json.loads((Path(folder) / "dataset-metadata.json").read_text())
        self.calls.append(("version", notes, kw))
        return SimpleNamespace(error="", url="u")

    def dataset_create_new(self, folder, public, **kw):
        self.calls.append(("create", public, kw))
        return SimpleNamespace(error="", url="u")


def http_error(code):
    return requests.exceptions.HTTPError(response=SimpleNamespace(status_code=code))


def test_dataset_exists():
    assert kaggle_sync.dataset_exists(FakeApi(), REF)
    assert not kaggle_sync.dataset_exists(FakeApi(http_error(404)), REF)
    assert not kaggle_sync.dataset_exists(FakeApi(http_error(403)), REF)
    with pytest.raises(requests.exceptions.HTTPError):
        kaggle_sync.dataset_exists(FakeApi(http_error(401)), REF)


def test_publish_keeps_parquet_and_picks_create_or_version(tmp_path):
    (tmp_path / "dataset-metadata.json").write_text(json.dumps({"keywords": ["finance"], "title": "t"}))
    api = FakeApi()
    kaggle_sync.publish(api, tmp_path, exists=True, notes="n", public=False)
    kaggle_sync.publish(api, tmp_path, exists=False, notes="n", public=False)
    assert [c[0] for c in api.calls] == ["version", "create"]
    assert "keywords" not in api.sent_meta  # tags are set by update_settings, never added by a version
    assert json.loads((tmp_path / "dataset-metadata.json").read_text())["keywords"] == ["finance"]
    assert all(c[2]["convert_to_csv"] is False for c in api.calls)


def test_publish_raises_on_kaggle_error(tmp_path):
    (tmp_path / "dataset-metadata.json").write_text("{}")
    api = FakeApi()
    api.dataset_create_version = lambda *a, **k: SimpleNamespace(error="bad", url="")
    with pytest.raises(RuntimeError, match="bad"):
        kaggle_sync.publish(api, Path(tmp_path), exists=True, notes="n", public=False)


def test_metadata_has_sources_frequency_and_cover(tmp_path):
    run(tmp_path / "v1", None, DAY1)
    meta = json.loads((tmp_path / "v1" / "dataset-metadata.json").read_text())
    assert meta["expectedUpdateFrequency"] == "daily"
    assert "DefiLlama" in meta["userSpecifiedSources"]
    assert (tmp_path / "v1" / "dataset-cover-image.png").is_file()


class FakeSettingsApi:
    def __init__(self, current, fail=False):
        self.current, self.fail, self.sent = current, fail, None

    def dataset_metadata(self, ref, path):
        p = Path(path) / "dataset-metadata.json"
        p.write_text(json.dumps({"info": self.current}))
        return str(p)

    def dataset_list(self, user=None, search=None):
        thumb = "https://x/default-backdrop.png" if self.default_cover else "https://x/cover.png"
        return [SimpleNamespace(ref=REF, thumbnail_image_url=thumb)]

    default_cover = False
    updates = 0

    def dataset_metadata_update(self, ref, path):
        self.updates += 1
        if self.fail == "flaky":
            self.fail = False
            raise requests.exceptions.ConnectionError("connection reset")
        if self.fail == "empty reply":  # HTTP 200 with an empty body: applied, but unparseable
            self.sent = json.loads((Path(path) / "dataset-metadata.json").read_text())
            raise requests.exceptions.JSONDecodeError("Expecting value", "", 0)
        if self.fail == "once":
            self.fail = False
            raise SystemExit(1)
        if self.fail:
            raise SystemExit(1)
        self.sent = json.loads((Path(path) / "dataset-metadata.json").read_text())


@pytest.mark.parametrize("is_private", [True, False])
def test_update_settings_keeps_visibility_and_collaborators(tmp_path, is_private):
    (tmp_path / "dataset-metadata.json").write_text(json.dumps({"title": "t", "resources": []}))
    collaborators = [{"username": "friend", "role": "writer"}]
    api = FakeSettingsApi({"isPrivate": is_private, "collaborators": collaborators})
    kaggle_sync.update_settings(api, tmp_path, REF)
    assert api.sent["isPrivate"] is is_private
    assert api.sent["collaborators"] == collaborators


def test_update_settings_missing_private_flag_means_public(tmp_path):
    (tmp_path / "dataset-metadata.json").write_text("{}")
    api = FakeSettingsApi({"title": "t"})  # what Kaggle returns for a public dataset
    kaggle_sync.update_settings(api, tmp_path, REF)
    assert api.sent["isPrivate"] is False


def test_update_settings_failure_raises(tmp_path):
    (tmp_path / "dataset-metadata.json").write_text("{}")
    api = FakeSettingsApi({"isPrivate": True}, fail=True)
    with pytest.raises(RuntimeError, match="settings update failed"):
        kaggle_sync.update_settings(api, tmp_path, REF, pause_s=0)
    assert api.updates == 3  # retried: Kaggle can reject it while a new version's files are processed


def test_update_settings_retries_while_new_files_are_processed(tmp_path):
    (tmp_path / "dataset-metadata.json").write_text("{}")
    api = FakeSettingsApi({"isPrivate": True}, fail="once")
    kaggle_sync.update_settings(api, tmp_path, REF, pause_s=0)
    assert api.updates == 2 and api.sent is not None


def test_wait_until_ready_polls_then_fails_on_error():
    statuses = iter(["pending", "ready"])
    api = SimpleNamespace(dataset_status=lambda ref: next(statuses))
    kaggle_sync.wait_until_ready(api, REF, poll_s=0)
    with pytest.raises(RuntimeError, match="'error'"):
        kaggle_sync.wait_until_ready(SimpleNamespace(dataset_status=lambda ref: "error"), REF, poll_s=0)


class FakeFilesApi:
    """Lists two files and serves them, failing the first `fail_first` downloads with 404."""

    def __init__(self, fail_first=0, wrong_size=False):
        self.fail_first, self.wrong_size, self.calls = fail_first, wrong_size, []

    def dataset_status(self, ref):
        return "ready"

    def dataset_list_files(self, ref, page_token=None):
        files = [SimpleNamespace(name="a.csv", total_bytes=3), SimpleNamespace(name="b.parquet", total_bytes=4)]
        return SimpleNamespace(files=files, nextPageToken="")

    def dataset_download_file(self, ref, name, path, **kw):
        self.calls.append(name)
        if len(self.calls) <= self.fail_first:
            raise http_error(404)
        content = b"xyz" if name == "a.csv" else (b"x" if self.wrong_size else b"wxyz")
        (Path(path) / name).write_bytes(content)


def test_download_fetches_each_file_and_retries_while_processing(tmp_path):
    api = FakeFilesApi(fail_first=2)
    kaggle_sync.download_current(api, REF, tmp_path, pause_s=0)
    assert api.calls == ["a.csv", "a.csv", "a.csv", "b.parquet"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.csv", "b.parquet"]

    with pytest.raises(requests.exceptions.HTTPError):
        kaggle_sync.download_current(FakeFilesApi(fail_first=10), REF, tmp_path, attempts=2, pause_s=0)


def test_download_refuses_a_truncated_file(tmp_path):
    with pytest.raises(RuntimeError, match="not publishing"):
        kaggle_sync.download_current(FakeFilesApi(wrong_size=True), REF, tmp_path, pause_s=0)


def test_history_may_lose_a_member_but_not_days(tmp_path):
    def chains(series_by_chain):
        f = fetchers(DAY1)
        f["chain_tvl_history"] = lambda prev: transform.chain_tvl_history(series_by_chain)
        return f

    # Day 1: chains A (1200 days) and X (50 days). Day 2: X left the top list.
    pipeline.build(SPEC, tmp_path / "v1", None, DAY1, REF,
                   fetchers=chains({"A": fakes.tvl_series(), "X": fakes.tvl_series(50)}))
    report = pipeline.build(SPEC, tmp_path / "v2", tmp_path / "v1", DAY2, REF,
                            fetchers=chains({"A": fakes.tvl_series()}))
    assert "chain_tvl_history" not in report.failed
    assert len(pd.read_csv(tmp_path / "v2" / "chain_tvl_history.csv")) == 1200

    # Losing days of history is still refused.
    report = pipeline.build(SPEC, tmp_path / "v3", tmp_path / "v2", DAY2, REF,
                            fetchers=chains({"A": fakes.tvl_series(1100)}))
    assert "would shrink from 1200 to 1100 days" in report.failed["chain_tvl_history"]


def test_update_settings_retries_transient_errors(tmp_path):
    (tmp_path / "dataset-metadata.json").write_text("{}")
    api = FakeSettingsApi({"isPrivate": True}, fail="flaky")
    kaggle_sync.update_settings(api, tmp_path, REF, pause_s=0)
    assert api.sent is not None


def test_wait_until_ready_tolerates_just_created_dataset():
    answers = iter([http_error(403), http_error(404), "ready"])

    def status(ref):
        a = next(answers)
        if isinstance(a, Exception):
            raise a
        return a
    kaggle_sync.wait_until_ready(SimpleNamespace(dataset_status=status), REF, poll_s=0)


def test_update_settings_reuses_kaggles_license_name(tmp_path):
    (tmp_path / "dataset-metadata.json").write_text(json.dumps({"licenses": [{"name": "CC-BY-4.0"}]}))
    stored = [{"name": "Attribution 4.0 International (CC BY 4.0)"}]
    api = FakeSettingsApi({"isPrivate": True, "licenses": stored})
    kaggle_sync.update_settings(api, tmp_path, REF)
    assert api.sent["licenses"] == stored


def test_update_settings_reapplies_when_cover_did_not_stick(tmp_path, monkeypatch):
    monkeypatch.setattr(kaggle_sync.time, "sleep", lambda s: None)
    (tmp_path / "dataset-metadata.json").write_text("{}")
    (tmp_path / "dataset-cover-image.png").write_bytes(b"png")
    api = FakeSettingsApi({"isPrivate": False})
    api.default_cover = True
    kaggle_sync.update_settings(api, tmp_path, REF)
    assert api.updates == 2
    ok = FakeSettingsApi({"isPrivate": False})
    kaggle_sync.update_settings(ok, tmp_path, REF)
    assert ok.updates == 1


def test_update_settings_accepts_an_empty_reply(tmp_path):
    (tmp_path / "dataset-metadata.json").write_text("{}")
    api = FakeSettingsApi({"isPrivate": False}, fail="empty reply")
    kaggle_sync.update_settings(api, tmp_path, REF, pause_s=0)
    assert api.updates == 1 and api.sent is not None


def test_update_settings_can_make_a_dataset_public(tmp_path):
    (tmp_path / "dataset-metadata.json").write_text("{}")
    api = FakeSettingsApi({"isPrivate": True})
    kaggle_sync.update_settings(api, tmp_path, REF, make_public=True)
    assert api.sent["isPrivate"] is False
