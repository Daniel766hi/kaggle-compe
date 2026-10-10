"""DeFi Daily: TVL, stablecoins, DEX volume and yields from the DefiLlama API."""

from pathlib import Path

from ...schema import DatasetSpec, files_markdown
from . import sources, transform
from .tables import TABLES

ASSETS = Path(__file__).resolve().parents[3] / "assets"


def make_fetchers(session, snapshot_date):
    cache = {}

    def chains():
        if "chains" not in cache:
            cache["chains"] = transform.chains_snapshot(sources.fetch_chains(session), snapshot_date)
        return cache["chains"]

    return {
        "defi_tvl_history": lambda prev: transform.defi_tvl_history(sources.fetch_defi_tvl_history(session)),
        "chain_tvl_history": lambda prev: transform.chain_tvl_history(
            sources.fetch_chain_tvl_histories(session, transform.top_chains(chains()))
        ),
        "stablecoin_supply_history": lambda prev: transform.stablecoin_supply_history(
            sources.fetch_stablecoin_supply_history(session)
        ),
        "dex_fees_history": lambda prev: transform.dex_fees_history(
            sources.fetch_dex_overview(session), sources.fetch_fees_overview(session)
        ),
        "protocols_snapshots": lambda prev: transform.protocols_snapshot(
            sources.fetch_protocols(session), snapshot_date
        ),
        "chains_snapshots": lambda prev: chains(),
        "stablecoins_snapshots": lambda prev: transform.stablecoins_snapshot(
            sources.fetch_stablecoins(session), snapshot_date
        ),
        "yield_pools_snapshots": lambda prev: transform.yield_pools_snapshot(
            sources.fetch_yield_pools(session), snapshot_date
        ),
    }


def describe(snapshot_date, tables_written):
    return "\n".join([
        "Daily-updated data on decentralized finance (DeFi): total value locked (TVL), "
        "blockchains, stablecoins, DEX trading volume, protocol fees and yield pools.",
        "",
        "## Why this dataset",
        "",
        "The API's list endpoints only return the *current* state of every protocol, stablecoin "
        "and yield pool. This dataset saves that state every day, so the `*_snapshots.parquet` "
        "files grow into one ready-to-use, day-by-day panel instead of thousands of separate API "
        "calls. Use it to study protocol growth, stablecoin market share, yield changes, or "
        "category trends over time.",
        "",
        "## Files",
        "",
        files_markdown(tables_written),
        "",
        "## Updates",
        "",
        f"Refreshed daily by an automated pipeline. Last update: {snapshot_date:%Y-%m-%d} (UTC). "
        "Snapshot panels start on the first day the pipeline ran.",
        "",
        "## Source and attribution",
        "",
        "All data comes from the free public [DefiLlama API](https://defillama.com/docs/api). "
        "Please credit **DefiLlama** when you use this data. Values are as reported by DefiLlama "
        "and can be revised by them later; history files are re-downloaded in full each day.",
        "",
        "## Notes",
        "",
        "- All amounts are in USD unless stated otherwise. Dates are UTC.",
        f"- Yield pools are limited to pools with at least ${transform.MIN_POOL_TVL_USD:,.0f} TVL.",
        f"- `chain_tvl_history` covers the {transform.TOP_CHAINS_FOR_HISTORY} largest chains by current TVL.",
        "- `protocols_snapshots` includes CEX entries (category `CEX`); filter them out for pure DeFi.",
    ])


SPEC = DatasetSpec(
    name="defi",
    slug="defi-daily-tvl-stablecoins-dex-yields",
    title="DeFi Daily: TVL, Stablecoins, DEX & Yields",
    subtitle="Daily-updated DeFi TVL, chain, stablecoin, DEX volume and yield pool data",
    license="other",
    keywords=["finance", "economics", "investing", "time series analysis"],
    tables=TABLES,
    sources=(
        "DefiLlama public API (https://defillama.com/docs/api): "
        "api.llama.fi (/protocols, /v2/chains, /v2/historicalChainTvl, /overview/dexs, /overview/fees), "
        "stablecoins.llama.fi (/stablecoins, /stablecoincharts/all), yields.llama.fi (/pools). "
        "Collected daily by https://github.com/daniel766hi/kaggle-compe"
    ),
    make_fetchers=make_fetchers,
    describe=describe,
    cover=ASSETS / "defi-cover.png",
)
