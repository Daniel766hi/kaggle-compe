import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
import requests

from defi_dataset import config, kaggle_sync, pipeline, transform

from . import fakes

REF = "someone/defi-daily-tvl-stablecoins-dex-yields"
DAY1, DAY2 = pd.Timestamp("2026-10-09"), pd.Timestamp("2026-10-10")


def fetchers(snapshot_date, broken=()):
    def fail():
        raise requests.exceptions.ConnectionError("boom")

    f = {
        "defi_tvl_history": lambda: transform.defi_tvl_history(fakes.tvl_series()),
        "chain_tvl_history": lambda: transform.chain_tvl_history({"A": fakes.tvl_series()}),
        "stablecoin_supply_history": lambda: transform.stablecoin_supply_history(fakes.stablecoin_chart()),
        "dex_fees_history": lambda: transform.dex_fees_history(fakes.overview(), fakes.overview()),
        "protocols_snapshots": lambda: transform.protocols_snapshot(fakes.protocols(), snapshot_date),
        "chains_snapshots": lambda: transform.chains_snapshot(fakes.chains(), snapshot_date),
        "stablecoins_snapshots": lambda: transform.stablecoins_snapshot(fakes.stablecoins(), snapshot_date),
        "yield_pools_snapshots": lambda: transform.yield_pools_snapshot(fakes.yield_pools(), snapshot_date),
    }
    return {name: (fail if name in broken else fn) for name, fn in f.items()}


def run(out, previous, day, broken=()):
    return pipeline.build(out, previous, day, REF, fetchers=fetchers(day, broken))


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
    f["protocols_snapshots"] = lambda: transform.protocols_snapshot(fakes.protocols(3), DAY1)
    report = pipeline.build(tmp_path / "v1", None, DAY1, REF, fetchers=f)
    assert "only 3 rows" in report.failed["protocols_snapshots"]
    assert not (tmp_path / "v1" / "protocols_snapshots.parquet").exists()


def test_shorter_history_than_before_is_rejected(tmp_path):
    run(tmp_path / "v1", None, DAY1)
    f = fetchers(DAY2)
    f["defi_tvl_history"] = lambda: transform.defi_tvl_history(fakes.tvl_series(1100))
    report = pipeline.build(tmp_path / "v2", tmp_path / "v1", DAY2, REF, fetchers=f)
    assert "would shrink" in report.failed["defi_tvl_history"]
    assert len(pd.read_csv(tmp_path / "v2" / "defi_tvl_history.csv")) == 1200


def test_everything_failing_aborts(tmp_path):
    with pytest.raises(RuntimeError, match="Every source failed"):
        run(tmp_path / "v1", None, DAY1, broken=set(fetchers(DAY1)))


def test_config_lengths_fit_kaggle_limits():
    assert 6 <= len(config.DATASET_TITLE) <= 50
    assert 20 <= len(config.DATASET_SUBTITLE) <= 80
    assert 6 <= len(config.DATASET_SLUG) <= 50


class FakeApi:
    def __init__(self, status_error=None):
        self.status_error = status_error
        self.calls = []

    def dataset_status(self, ref):
        if self.status_error:
            raise self.status_error
        return "ready"

    def dataset_create_version(self, folder, notes, **kw):
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
    api = FakeApi()
    kaggle_sync.publish(api, tmp_path, exists=True, notes="n", public=False)
    kaggle_sync.publish(api, tmp_path, exists=False, notes="n", public=False)
    assert [c[0] for c in api.calls] == ["version", "create"]
    assert all(c[2]["convert_to_csv"] is False for c in api.calls)


def test_publish_raises_on_kaggle_error(tmp_path):
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

    def dataset_metadata_update(self, ref, path):
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
    with pytest.raises(RuntimeError, match="settings update failed"):
        kaggle_sync.update_settings(FakeSettingsApi({"isPrivate": True}, fail=True), tmp_path, REF)


def test_wait_until_ready_polls_then_fails_on_error():
    statuses = iter(["pending", "ready"])
    api = SimpleNamespace(dataset_status=lambda ref: next(statuses))
    kaggle_sync.wait_until_ready(api, REF, poll_s=0)
    with pytest.raises(RuntimeError, match="'error'"):
        kaggle_sync.wait_until_ready(SimpleNamespace(dataset_status=lambda ref: "error"), REF, poll_s=0)
