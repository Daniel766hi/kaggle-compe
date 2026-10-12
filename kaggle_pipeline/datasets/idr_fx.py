"""Rupiah (IDR) daily exchange rates, from the ECB euro reference rates via the Frankfurter API."""

import logging
from datetime import date
from pathlib import Path

import pandas as pd

from ..http import get_json
from ..schema import Column, DatasetSpec, Table, files_markdown

log = logging.getLogger(__name__)

ASSETS = Path(__file__).resolve().parents[2] / "assets"
# frankfurter.app is the original host; api.frankfurter.dev/v1 is the newer one. Use whichever answers.
BASE_URLS = ("https://api.frankfurter.dev/v1", "https://api.frankfurter.app")
FIRST_DAY = date(1999, 1, 4)  # first ECB reference rate

# Columns of the wide table, in this order. Discontinued currencies stay in the long table only.
WIDE_CURRENCIES = [
    "EUR", "USD", "JPY", "GBP", "CHF", "AUD", "CAD", "NZD", "CNY", "HKD", "SGD", "MYR", "THB", "PHP",
    "KRW", "INR", "SEK", "NOK", "DKK", "PLN", "CZK", "HUF", "RON", "BGN", "TRY", "ILS", "BRL", "MXN",
    "ZAR", "ISK",
]
MONTHLY_CURRENCIES = ["USD", "EUR", "SGD", "JPY", "CNY", "MYR", "AUD", "GBP", "HKD", "KRW", "THB", "INR"]

TABLES = [
    Table(
        name="ecb_reference_rates",
        kind="history",
        description="Raw ECB euro reference rates: units of each currency per 1 EUR, every TARGET working day.",
        columns=[
            Column("date", "datetime", "Rate date (ECB publishes around 16:00 CET)"),
            Column("currency", "string", "ISO 4217 currency code"),
            Column("rate_per_eur", "number", "Units of the currency per 1 EUR"),
        ],
        min_rows=100_000,
        key=("date", "currency"),
    ),
    Table(
        name="idr_exchange_rates",
        kind="derived",
        description="Rupiah per 1 unit of 30 major currencies, one row per day (wide format).",
        columns=[Column("date", "datetime", "Rate date")]
        + [Column(f"idr_per_{c.lower()}", "number", f"Indonesian rupiah per 1 {c}") for c in WIDE_CURRENCIES],
        key=("date",),
    ),
    Table(
        name="idr_monthly_average",
        kind="derived",
        description="Monthly average, low and high rupiah rate for 12 currencies important to Indonesian trade.",
        columns=[
            Column("month", "datetime", "First day of the month"),
            Column("currency", "string", "ISO 4217 currency code"),
            Column("idr_per_unit_mean", "number", "Average rupiah per 1 unit over the month"),
            Column("idr_per_unit_min", "number", "Strongest rupiah rate in the month (fewest IDR per unit)"),
            Column("idr_per_unit_max", "number", "Weakest rupiah rate in the month (most IDR per unit)"),
            Column("trading_days", "integer", "Number of days with a published rate"),
        ],
        key=("month", "currency"),
    ),
]


def fetch_rates(session, start, end):
    """Return {date string: {currency: rate per EUR}} for [start, end], one request per year."""
    errors = []
    for base in BASE_URLS:
        try:
            rates = {}
            for year in range(start.year, end.year + 1):
                lo, hi = max(start, date(year, 1, 1)), min(end, date(year, 12, 31))
                data = get_json(session, f"{base}/{lo:%Y-%m-%d}..{hi:%Y-%m-%d}")
                rates.update(data.get("rates") or {})
            return rates
        except Exception as exc:  # noqa: BLE001 - try the other host
            errors.append(f"{base}: {exc}")
            log.warning("Frankfurter host failed, trying next: %s", exc)
    raise RuntimeError("; ".join(errors))


def rates_to_frame(rates):
    rows = [
        {"date": day, "currency": cur, "rate_per_eur": value}
        for day, by_currency in rates.items()
        for cur, value in (by_currency or {}).items()
    ]
    return pd.DataFrame(rows, columns=["date", "currency", "rate_per_eur"])


def idr_wide(ecb):
    by_cur = ecb.pivot_table(index="date", columns="currency", values="rate_per_eur")
    if "IDR" not in by_cur:
        return pd.DataFrame(columns=["date"])
    by_cur = by_cur[by_cur["IDR"].notna()]
    out = pd.DataFrame({"date": by_cur.index})
    for cur in WIDE_CURRENCIES:
        # 1 EUR = IDR rupiah = X units of cur  ->  1 cur = IDR / X rupiah
        per_eur = by_cur["IDR"].to_numpy()
        out[f"idr_per_{cur.lower()}"] = per_eur if cur == "EUR" else (
            per_eur / by_cur[cur].to_numpy() if cur in by_cur else float("nan")
        )
    return out


def idr_monthly(wide):
    long = wide.melt(id_vars="date", var_name="col", value_name="idr_per_unit").dropna(subset=["idr_per_unit"])
    long["currency"] = long["col"].str.removeprefix("idr_per_").str.upper()
    long = long[long["currency"].isin(MONTHLY_CURRENCIES)]
    long["month"] = long["date"].dt.to_period("M").dt.to_timestamp()
    agg = long.groupby(["month", "currency"])["idr_per_unit"].agg(["mean", "min", "max", "count"]).reset_index()
    return agg.rename(columns={
        "mean": "idr_per_unit_mean", "min": "idr_per_unit_min", "max": "idr_per_unit_max", "count": "trading_days",
    })


def make_fetchers(session, snapshot_date):
    return {
        "ecb_reference_rates": lambda prev: rates_to_frame(
            fetch_rates(session, FIRST_DAY, snapshot_date.date())
        ),
    }


def derive(frames):
    wide = idr_wide(frames["ecb_reference_rates"])
    return {"idr_exchange_rates": wide, "idr_monthly_average": idr_monthly(wide)}


def describe(snapshot_date, tables_written, frames=None):
    return "\n".join([
        "Daily exchange rates of the **Indonesian rupiah (IDR)** against 30 major currencies "
        "(USD, EUR, SGD, JPY, CNY, MYR and more), plus the full set of ECB euro reference rates.",
        "",
        "## Why this dataset",
        "",
        "Ready-to-use rupiah rates in one tidy table: one row per day, one column per currency, "
        "already converted to *rupiah per 1 unit*. Useful for import/export cost analysis, "
        "inflation and macro studies, forecasting practice, or converting any IDR financial data.",
        "",
        "## Files",
        "",
        files_markdown(tables_written),
        "",
        "## How the rupiah rates are computed",
        "",
        "The ECB publishes how many units of each currency equal 1 euro. The rupiah rate against "
        "another currency X is the cross rate `IDR per EUR / X per EUR`. For example, if 1 EUR = "
        "17,500 IDR and 1 EUR = 1.10 USD, then 1 USD = 15,909 IDR.",
        "",
        "## Updates",
        "",
        f"Refreshed daily by an automated pipeline. Last update: {snapshot_date:%Y-%m-%d} (UTC). "
        "The ECB publishes rates on TARGET working days only, so weekends and holidays have no row.",
        "",
        "## Source and attribution",
        "",
        "Source: **European Central Bank** euro foreign exchange reference rates, retrieved through "
        "the open-source [Frankfurter API](https://frankfurter.dev). ECB statistics may be reused "
        "free of charge with the source acknowledged.",
        "",
        "## Notes",
        "",
        "- These are ECB *reference* rates (about 14:15 CET), for information purposes. They are not "
        "Bank Indonesia's JISDOR rate or bank buy/sell rates, and can differ slightly from them.",
        "- Currencies the ECB stopped publishing (for example RUB) appear only in `ecb_reference_rates.csv`.",
    ])


SPEC = DatasetSpec(
    name="idr-fx",
    slug="rupiah-idr-daily-exchange-rates",
    title="Rupiah (IDR) Daily Exchange Rates",
    subtitle="Daily rupiah rates vs USD, EUR, SGD, JPY, CNY and 25 more, from ECB data",
    license="other",
    keywords=["currencies and foreign exchange", "finance", "economics", "asia", "time series analysis"],
    tables=TABLES,
    sources=(
        "European Central Bank euro foreign exchange reference rates "
        "(https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/), "
        "retrieved via the Frankfurter API (https://frankfurter.dev). "
        "Collected daily by https://github.com/daniel766hi/kaggle-compe"
    ),
    make_fetchers=make_fetchers,
    describe=describe,
    derive=derive,
    cover=ASSETS / "idr-fx-cover.png",
)
