import os

# Kaggle dataset identity. The owner must be your Kaggle username.
KAGGLE_OWNER = os.environ.get("KAGGLE_USERNAME") or ""
# `or` rather than a get() default: GitHub Actions passes unset variables as empty strings.
DATASET_SLUG = os.environ.get("KAGGLE_DATASET_SLUG") or "defi-daily-tvl-stablecoins-dex-yields"

# Kaggle limits: title 6-50 chars, subtitle 20-80 chars.
DATASET_TITLE = "DeFi Daily: TVL, Stablecoins, DEX & Yields"
DATASET_SUBTITLE = "Daily-updated DeFi TVL, chain, stablecoin, DEX volume and yield pool data"
DATASET_LICENSE = "other"
DATASET_KEYWORDS = ["finance", "economics", "investing", "time series analysis"]

# Scraper settings
TOP_CHAINS_FOR_HISTORY = 25
MIN_POOL_TVL_USD = 1_000_000
REQUEST_TIMEOUT_S = 90
REQUEST_PAUSE_S = 1.0  # pause between per-chain requests, to be polite to the API
USER_AGENT = "defi-daily-kaggle-dataset/1.0 (+https://github.com/daniel766hi/kaggle-compe)"


def dataset_ref():
    if not KAGGLE_OWNER:
        raise RuntimeError("Set KAGGLE_USERNAME to your Kaggle username.")
    return f"{KAGGLE_OWNER}/{DATASET_SLUG}"
