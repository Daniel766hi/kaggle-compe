"""Thin HTTP layer over the public DefiLlama API (https://defillama.com/docs/api)."""

import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import config

API = "https://api.llama.fi"
STABLECOINS_API = "https://stablecoins.llama.fi"
YIELDS_API = "https://yields.llama.fi"


def make_session():
    session = requests.Session()
    retry = Retry(
        total=5,
        backoff_factor=2,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers["User-Agent"] = config.USER_AGENT
    return session


def get_json(session, url, params=None):
    resp = session.get(url, params=params, timeout=config.REQUEST_TIMEOUT_S)
    resp.raise_for_status()
    return resp.json()


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
        time.sleep(config.REQUEST_PAUSE_S)
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
