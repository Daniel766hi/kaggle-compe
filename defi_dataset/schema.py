"""Table definitions: one source of truth for files, dtypes and column docs.

Two kinds of table:
- "history": the API returns the full time series, so the file is rebuilt every run.
- "snapshot": the API only returns the current state, so each run appends one
  dated snapshot to a growing panel. This accumulated history is what makes the
  dataset worth more than calling the API directly.
"""

from dataclasses import dataclass, field

# Kaggle column types: string, integer, number, boolean, datetime
PANDAS_DTYPES = {
    "string": "string",
    "integer": "Int64",
    "number": "float64",
    "boolean": "boolean",
    "datetime": "datetime64[ns]",
}


@dataclass(frozen=True)
class Column:
    name: str
    type: str
    description: str


@dataclass(frozen=True)
class Table:
    name: str
    kind: str  # "history" or "snapshot"
    description: str
    columns: list = field(default_factory=list)
    # A fetch that returns fewer rows than this is treated as an API failure.
    min_rows: int = 1
    # Columns that identify one row (used for de-duplication).
    key: tuple = ()

    @property
    def file_name(self):
        return f"{self.name}.csv" if self.kind == "history" else f"{self.name}.parquet"

    @property
    def latest_file_name(self):
        return f"{self.name.removesuffix('_snapshots')}_latest.csv"

    @property
    def column_names(self):
        return [c.name for c in self.columns]


SNAPSHOT_DATE = Column("snapshot_date", "datetime", "UTC date the snapshot was taken")

TABLES = [
    Table(
        name="defi_tvl_history",
        kind="history",
        description="Daily total value locked (TVL) across all DeFi protocols and chains.",
        columns=[
            Column("date", "datetime", "UTC date"),
            Column("tvl_usd", "number", "Total value locked across DeFi, in USD"),
        ],
        min_rows=1000,
        key=("date",),
    ),
    Table(
        name="chain_tvl_history",
        kind="history",
        description="Daily TVL for the largest blockchains by current TVL.",
        columns=[
            Column("date", "datetime", "UTC date"),
            Column("chain", "string", "Blockchain name"),
            Column("tvl_usd", "number", "Total value locked on the chain, in USD"),
        ],
        min_rows=1000,
        key=("date", "chain"),
    ),
    Table(
        name="stablecoin_supply_history",
        kind="history",
        description="Daily total circulating supply of all tracked stablecoins, in USD.",
        columns=[
            Column("date", "datetime", "UTC date"),
            Column("total_circulating_usd", "number", "Total stablecoin supply across all peg types, in USD"),
        ],
        min_rows=500,
        key=("date",),
    ),
    Table(
        name="dex_fees_history",
        kind="history",
        description="Daily aggregate DEX trading volume and protocol fees across DeFi.",
        columns=[
            Column("date", "datetime", "UTC date"),
            Column("dex_volume_usd", "number", "Total DEX trading volume that day, in USD"),
            Column("fees_usd", "number", "Total fees paid by users to DeFi protocols that day, in USD"),
        ],
        min_rows=500,
        key=("date",),
    ),
    Table(
        name="protocols_snapshots",
        kind="snapshot",
        description="Daily snapshot of every DeFi protocol with a reported TVL. One row per protocol per day.",
        columns=[
            SNAPSHOT_DATE,
            Column("protocol_id", "string", "DefiLlama protocol ID"),
            Column("name", "string", "Protocol name"),
            Column("slug", "string", "DefiLlama URL slug"),
            Column("symbol", "string", "Governance token symbol, if any"),
            Column("category", "string", "Protocol category (e.g. Lending, Dexs, Liquid Staking)"),
            Column("primary_chain", "string", "Main chain, or 'Multi-Chain'"),
            Column("chains", "string", "All chains the protocol is deployed on, separated by '|'"),
            Column("n_chains", "integer", "Number of chains the protocol is deployed on"),
            Column("tvl_usd", "number", "Total value locked, in USD"),
            Column("change_1h_pct", "number", "TVL change over the last hour, in percent"),
            Column("change_1d_pct", "number", "TVL change over the last day, in percent"),
            Column("change_7d_pct", "number", "TVL change over the last 7 days, in percent"),
            Column("mcap_usd", "number", "Governance token market cap, in USD"),
            Column("parent_protocol", "string", "Parent protocol ID, if the protocol is part of a family"),
            Column("listed_at", "datetime", "When DefiLlama started tracking the protocol (UTC)"),
        ],
        min_rows=500,
        key=("snapshot_date", "protocol_id"),
    ),
    Table(
        name="chains_snapshots",
        kind="snapshot",
        description="Daily snapshot of TVL on every tracked blockchain. One row per chain per day.",
        columns=[
            SNAPSHOT_DATE,
            Column("chain", "string", "Blockchain name"),
            Column("tvl_usd", "number", "Total value locked on the chain, in USD"),
            Column("token_symbol", "string", "Native token symbol"),
            Column("chain_id", "string", "EVM chain ID, if applicable"),
        ],
        min_rows=50,
        key=("snapshot_date", "chain"),
    ),
    Table(
        name="stablecoins_snapshots",
        kind="snapshot",
        description="Daily snapshot of every tracked stablecoin. One row per stablecoin per day.",
        columns=[
            SNAPSHOT_DATE,
            Column("stablecoin_id", "string", "DefiLlama stablecoin ID"),
            Column("name", "string", "Stablecoin name"),
            Column("symbol", "string", "Ticker symbol"),
            Column("peg_type", "string", "What the coin is pegged to (e.g. peggedUSD, peggedEUR)"),
            Column("peg_mechanism", "string", "How the peg is maintained (fiat-backed, crypto-backed, algorithmic)"),
            Column("circulating", "number", "Circulating supply in units of the peg"),
            Column("circulating_prev_day", "number", "Circulating supply one day earlier"),
            Column("circulating_prev_week", "number", "Circulating supply one week earlier"),
            Column("circulating_prev_month", "number", "Circulating supply one month earlier"),
            Column("price", "number", "Market price in USD"),
            Column("n_chains", "integer", "Number of chains the stablecoin is issued on"),
        ],
        min_rows=50,
        key=("snapshot_date", "stablecoin_id"),
    ),
    Table(
        name="yield_pools_snapshots",
        kind="snapshot",
        description="Daily snapshot of DeFi yield pools with at least $1M TVL. One row per pool per day.",
        columns=[
            SNAPSHOT_DATE,
            Column("pool_id", "string", "DefiLlama pool UUID"),
            Column("chain", "string", "Blockchain"),
            Column("project", "string", "Protocol offering the pool"),
            Column("symbol", "string", "Pool token symbol(s)"),
            Column("pool_meta", "string", "Extra pool details (e.g. lock period), if any"),
            Column("tvl_usd", "number", "Value locked in the pool, in USD"),
            Column("apy", "number", "Total APY in percent (base + reward)"),
            Column("apy_base", "number", "APY from fees or interest, in percent"),
            Column("apy_reward", "number", "APY from token incentives, in percent"),
            Column("apy_mean_30d", "number", "Average APY over the last 30 days, in percent"),
            Column("stablecoin", "boolean", "True if the pool only holds stablecoins"),
            Column("il_risk", "string", "Impermanent loss risk ('yes' or 'no')"),
            Column("exposure", "string", "'single' or 'multi' asset exposure"),
            Column("volume_usd_1d", "number", "Trading volume through the pool in the last day, in USD"),
        ],
        min_rows=200,
        key=("snapshot_date", "pool_id"),
    ),
]

TABLES_BY_NAME = {t.name: t for t in TABLES}
