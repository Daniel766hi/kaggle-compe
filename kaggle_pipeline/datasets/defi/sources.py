"""Thin HTTP layer over the public DefiLlama API (https://defillama.com/docs/api)."""

import time

import requests

from ...http import get_json

REQUEST_PAUSE_S = 1.0  # between per-chain requests, to be polite to the API

API = "https://api.llama.fi"
STABLECOINS_API = "https://stablecoins.llama.fi"
YIELDS_API = "https://yields.llama.fi"




def fetch_protocols(session):
    return get_json(session, f"{API}/protocols")


def fetch_chains(session):
    return get_json(session, f"{API}/v2/chains")


def fetch_defi_tvl_history(session):
    return get_json(session, f"{API}/v2/historicalChainTvl")


def fetch_chain_tvl_histories(session, chain_names):
    """Returns {chain_name: [{date, tvl}, ...]} for each requested chain."""
    out = {}
    for name in chain_names:
        out[name] = get_json(session, f"{API}/v2/historicalChainTvl/{requests.utils.quote(name)}")
        time.sleep(REQUEST_PAUSE_S)
    return out


def fetch_stablecoins(session):
    return get_json(session, f"{STABLECOINS_API}/stablecoins", params={"includePrices": "true"})


def fetch_stablecoin_supply_history(session):
    return get_json(session, f"{STABLECOINS_API}/stablecoincharts/all")


def _overview(session, kind):
    return get_json(
        session,
        f"{API}/overview/{kind}",
        params={"excludeTotalDataChart": "false", "excludeTotalDataChartBreakdown": "true"},
    )


def fetch_dex_overview(session):
    return _overview(session, "dexs")


def fetch_fees_overview(session):
    return _overview(session, "fees")


def fetch_yield_pools(session):
    return get_json(session, f"{YIELDS_API}/pools")
