"""The same fair test conditions for every strategy: python make_config.py EXCHANGE > config.json

1,000 USDT pretend wallet, up to 6 trades at once sharing it, the exchange's normal fees, and
the same 30 big, long-lived coins. Strategies keep their own timeframe and rules.
"""

import json
import sys

PAIRS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX", "DOT", "LINK", "LTC", "TRX", "BCH", "ATOM", "NEAR",
         "UNI", "FIL", "ETC", "XLM", "ALGO", "AAVE", "ICP", "HBAR", "VET", "APT", "ARB", "OP", "INJ", "SUI", "SAND"]  # fmt: skip

config = {
    "dry_run": True,
    "dry_run_wallet": 1000,
    "stake_currency": "USDT",
    "stake_amount": "unlimited",
    "tradable_balance_ratio": 0.99,
    "max_open_trades": 6,
    "trading_mode": "spot",
    "dataformat_ohlcv": "feather",
    "unfilledtimeout": {"entry": 3, "exit": 2, "exit_timeout_count": 0, "unit": "minutes"},
    "order_types": {"entry": "limit", "exit": "limit", "emergency_exit": "limit", "force_entry": "limit",
                    "force_exit": "limit", "stoploss": "limit", "stoploss_on_exchange": False},  # fmt: skip
    "entry_pricing": {"price_side": "other", "use_order_book": False, "order_book_top": 1, "price_last_balance": 0,
                      "check_depth_of_market": {"enabled": False, "bids_to_ask_delta": 1}},  # fmt: skip
    "exit_pricing": {"price_side": "other", "use_order_book": False, "order_book_top": 1},
    "exchange": {"name": sys.argv[1], "key": "", "secret": "", "pair_whitelist": [f"{p}/USDT" for p in PAIRS],
                 "pair_blacklist": []},  # fmt: skip
    "pairlists": [{"method": "StaticPairList"}],
    "internals": {"process_throttle_secs": 5},
}
json.dump(config, sys.stdout, indent=2)
