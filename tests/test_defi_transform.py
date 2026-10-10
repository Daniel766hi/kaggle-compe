import pandas as pd

from kaggle_pipeline.datasets.defi import transform
from kaggle_pipeline.datasets.defi.tables import TABLES_BY_NAME

from . import defi_fakes as fakes

SNAP = pd.Timestamp("2026-10-10")


def assert_matches_schema(df, name):
    assert list(df.columns) == TABLES_BY_NAME[name].column_names


def test_defi_tvl_history_converts_unix_to_dates():
    df = transform.defi_tvl_history(fakes.tvl_series(3))
    assert_matches_schema(df, "defi_tvl_history")
    assert df["date"].tolist() == list(pd.date_range(pd.Timestamp(fakes.START, unit="s"), periods=3))
    assert df["tvl_usd"].iloc[0] == 1e9


def test_chain_tvl_history_long_format():
    df = transform.chain_tvl_history({"A": fakes.tvl_series(2), "B": fakes.tvl_series(3)})
    assert_matches_schema(df, "chain_tvl_history")
    assert df.groupby("chain").size().to_dict() == {"A": 2, "B": 3}


def test_stablecoin_history_sums_all_pegs_and_parses_string_dates():
    df = transform.stablecoin_supply_history(fakes.stablecoin_chart(2))
    assert df["total_circulating_usd"].tolist() == [105.0, 105.0]
    assert df["date"].notna().all()


def test_dex_fees_outer_join_keeps_days_missing_from_one_side():
    df = transform.dex_fees_history(fakes.overview(3), fakes.overview(3, offset=1, value=2.0))
    assert len(df) == 4
    assert pd.isna(df["fees_usd"].iloc[0])
    assert pd.isna(df["dex_volume_usd"].iloc[-1])


def test_protocols_snapshot():
    df = transform.protocols_snapshot(fakes.protocols(4), SNAP)
    assert_matches_schema(df, "protocols_snapshots")
    assert len(df) == 4  # the protocol without TVL is dropped
    assert (df["snapshot_date"] == SNAP).all()
    assert df["chains"].iloc[0] == "Ethereum|Arbitrum"
    assert df["n_chains"].iloc[0] == 2
    assert pd.isna(df.loc[df["protocol_id"] == "0", "symbol"].iloc[0])  # "-" means no token
    assert df["listed_at"].iloc[0] == pd.Timestamp(fakes.START + 3600, unit="s")


def test_stablecoins_snapshot_reads_amount_for_own_peg():
    df = transform.stablecoins_snapshot(fakes.stablecoins(2), SNAP)
    assert_matches_schema(df, "stablecoins_snapshots")
    by_id = df.set_index("stablecoin_id")
    assert by_id.loc["0", "circulating"] == 7.0  # EUR coin uses its peggedEUR amount
    assert by_id.loc["1", "circulating"] == 101.0
    assert pd.isna(by_id.loc["1", "circulating_prev_month"])


def test_yield_pools_filtered_by_tvl():
    df = transform.yield_pools_snapshot(fakes.yield_pools(5), SNAP)
    assert_matches_schema(df, "yield_pools_snapshots")
    assert len(df) == 5
    assert df["stablecoin"].all()


def test_chains_snapshot_and_top_chains():
    df = transform.chains_snapshot(fakes.chains(5), SNAP)
    assert df["chain_id"].isna().sum() == 3
    assert transform.top_chains(df, 2) == ["Chain0", "Chain1"]


def test_conform_dedupes_on_key_and_adds_missing_columns():
    table = TABLES_BY_NAME["chains_snapshots"]
    raw = pd.DataFrame({"snapshot_date": [SNAP, SNAP], "chain": ["A", "A"], "tvl_usd": [1, 2]})
    df = transform.conform(raw, table)
    assert len(df) == 1 and df["tvl_usd"].iloc[0] == 2
    assert df["token_symbol"].isna().all()
