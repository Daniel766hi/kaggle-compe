"""Synthetic payloads shaped like the DefiLlama API responses the pipeline reads.

Only the fields the transforms use are included. Sizes are configurable so the
pipeline's minimum-row checks can be exercised.
"""

DAY = 86_400
START = 1_600_000_000 - 1_600_000_000 % DAY  # a UTC midnight


def tvl_series(n=1200, base=1e9):
    return [{"date": START + i * DAY, "tvl": base + i} for i in range(n)]


def chains(n=60):
    return [
        {"name": f"Chain{i}", "tvl": 1e9 - i * 1e6, "tokenSymbol": f"C{i}", "chainId": i if i % 2 else None,
         "gecko_id": None, "cmcId": None}
        for i in range(n)
    ]


def protocols(n=600):
    out = [
        {"id": str(i), "name": f"Proto{i}", "slug": f"proto-{i}", "symbol": "-" if i % 3 == 0 else f"P{i}",
         "category": "Lending", "chain": "Ethereum", "chains": ["Ethereum", "Arbitrum"], "tvl": 1e6 + i,
         "change_1h": 0.1, "change_1d": -1.5, "change_7d": 3.0, "mcap": None, "parentProtocol": None,
         "listedAt": START + 3600}
        for i in range(n)
    ]
    out.append({"id": "no-tvl", "name": "NoTvl", "tvl": None})  # must be skipped
    return out


def stablecoins(n=60):
    return {"peggedAssets": [
        {"id": str(i), "name": f"Stable{i}", "symbol": f"S{i}", "pegType": "peggedUSD" if i else "peggedEUR",
         "pegMechanism": "fiat-backed", "circulating": {"peggedUSD": 100.0 + i, "peggedEUR": 7.0},
         "circulatingPrevDay": {"peggedUSD": 99.0}, "circulatingPrevWeek": {}, "circulatingPrevMonth": None,
         "price": 1.0, "chains": ["Ethereum", "Tron"]}
        for i in range(n)
    ]}


def stablecoin_chart(n=600):
    # The real API returns dates as strings here.
    return [{"date": str(START + i * DAY), "totalCirculatingUSD": {"peggedUSD": 100.0, "peggedEUR": 5.0}}
            for i in range(n)]


def overview(n=600, offset=0, value=10.0):
    return {"totalDataChart": [[START + (i + offset) * DAY, value] for i in range(n)], "protocols": []}


def yield_pools(n=300):
    data = [
        {"pool": f"uuid-{i}", "chain": "Ethereum", "project": "aave-v3", "symbol": "USDC", "poolMeta": None,
         "tvlUsd": 2_000_000 + i, "apy": 5.0, "apyBase": 4.0, "apyReward": 1.0, "apyMean30d": 4.5,
         "stablecoin": True, "ilRisk": "no", "exposure": "single", "volumeUsd1d": None}
        for i in range(n)
    ]
    data.append({"pool": "tiny", "tvlUsd": 10.0})  # below the TVL filter
    return {"status": "success", "data": data}
