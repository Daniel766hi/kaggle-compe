"""Download WFP retail food prices for Indonesia (HDX) and build the calibration series.

Source: World Food Programme, "Indonesia - Food Prices", Humanitarian Data Exchange (HDX),
        https://data.humdata.org/dataset/wfp-food-prices-for-indonesia  (licence CC BY-IGO).
        WFP compiles these from Indonesian market price monitoring. Cite it with your access date.

Method (state this in Section 3.4):
  * Commodities: "Eggs" (telur ayam ras) and "Meat (chicken)" (daging ayam ras), retail, IDR/kg.
  * WFP gives ~200+ market-level monthly series but no recent national average, and the set of
    reporting markets changes in some months. To avoid composition bias, each market's price is
    divided by that market's own 2024 mean (the model baseline), and the national index for a month
    is the median of these market relatives. Nominal medians are kept for reference.
  * Months with fewer than MIN_MARKETS reporting markets, and the latest month if it may be
    incomplete, are flagged and excluded from calibration (use_for_calibration = False).
  * Each month is placed at model week = weeks since 1 Jan 2024 of the 15th of that month.

Usage:  python fetch_wfp_prices.py            (downloads)
        python fetch_wfp_prices.py file.csv   (uses a CSV you downloaded yourself)
"""
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from common import DATA_DIR

URL = ("https://data.humdata.org/dataset/72cc0659-142b-41af-821a-cb981a852617/resource/"
       "2c0e732c-1d93-4366-8f19-0397064ac5d7/download/wfp_food_prices_idn.csv")
COMMODITIES = {"Eggs": "egg", "Meat (chicken)": "chicken"}
MIN_MARKETS = 100
RAW_DIR = DATA_DIR / "raw"
RAW_DIR.mkdir(exist_ok=True)

src = sys.argv[1] if len(sys.argv) > 1 else URL
raw = pd.read_csv(src, skiprows=[1], low_memory=False, parse_dates=["date"])  # row 1 = HXL tags
x = raw[raw["commodity"].isin(COMMODITIES) & (raw["pricetype"] == "Retail") & (raw["unit"] == "KG")
        & (raw["date"] >= "2023-01-01") & (raw["market"] != "National Average")].copy()
x["series"] = x["commodity"].map(COMMODITIES)
x["month"] = x["date"].dt.to_period("M")

# keep a small, versionable extract of exactly the rows used (+ provenance)
x.drop(columns=["month"]).to_csv(RAW_DIR / "wfp_idn_eggs_chicken_extract.csv", index=False)
(RAW_DIR / "SOURCE.txt").write_text(
    f"World Food Programme (WFP). Indonesia - Food Prices. Humanitarian Data Exchange.\n{URL}\n"
    f"Licence: CC BY-IGO. Accessed: {date.today().isoformat()}.\n"
    f"Extract: commodities {list(COMMODITIES)}, retail, IDR/kg, market level, from 2023-01.\n")

rows = []
for s, g in x.groupby("series"):
    base = g[g["date"].dt.year == 2024].groupby("market")["price"].mean()
    g = g[g["market"].isin(base.index)].copy()
    g["rel"] = g["price"] / g["market"].map(base)
    m = g.groupby("month").agg(n_markets=("market", "nunique"), median_price=("price", "median"),
                               rel_index=("rel", "median"))
    m.columns = [f"{s}_{c}" for c in m.columns]
    rows.append(m)
monthly = pd.concat(rows, axis=1).sort_index()
monthly["week"] = [((p.to_timestamp() + pd.Timedelta(days=14)).date() - date(2024, 1, 1)).days // 7
                   for p in monthly.index]
monthly["min_markets"] = monthly[["egg_n_markets", "chicken_n_markets"]].min(axis=1)
monthly["use_for_calibration"] = monthly["min_markets"] >= MIN_MARKETS
last = monthly.index.max()
if last.to_timestamp(how="end").date() >= date.today():
    monthly.loc[last, "use_for_calibration"] = False      # month not finished yet
monthly.index = monthly.index.astype(str)
monthly.to_csv(DATA_DIR / "wfp_national_monthly.csv")

cal = monthly[(monthly["week"] >= 0) & monthly["use_for_calibration"]]
out = pd.DataFrame({"week": cal["week"].values, "rel_egg_price": cal["egg_rel_index"].values,
                    "rel_chicken_price": cal["chicken_rel_index"].values,
                    "month": cal.index, "n_markets": cal["min_markets"].values})
out.to_csv(DATA_DIR / "historical_prices.csv", index=False)

b = monthly.loc[monthly.index.str.startswith("2024")]
# ---- long national series 2007-2026 for seasonal estimation (pre-programme seasonality)
# 2007-01..2020-02: WFP "National Average" rows; from 2020-03: median across markets (months with
# >= MIN_MARKETS markets; thinner months left missing). Levels are not compared across the splice:
# seasonal_adjustment.py works with ratios to a centred 12-month moving average.
NA_MAP = {"Eggs": "egg", "Meat (chicken, broiler)": "chicken"}
MK_MAP = {"Eggs": "egg", "Meat (chicken)": "chicken"}
na = raw[(raw["market"] == "National Average") & raw["commodity"].isin(NA_MAP) & (raw["date"] < "2020-03-01")]
na = na.assign(series=na["commodity"].map(NA_MAP), month=na["date"].dt.to_period("M"))
long_na = na.pivot_table(index="month", columns="series", values="price", aggfunc="mean")
mk = raw[(raw["market"] != "National Average") & raw["commodity"].isin(MK_MAP) & (raw["pricetype"] == "Retail")
         & (raw["date"] >= "2020-03-01")]
mk = mk.assign(series=mk["commodity"].map(MK_MAP), month=mk["date"].dt.to_period("M"))
agg = mk.groupby(["month", "series"]).agg(p=("price", "median"), n=("market", "nunique")).reset_index()
agg.loc[agg["n"] < MIN_MARKETS, "p"] = float("nan")
long_mk = agg.pivot(index="month", columns="series", values="p")
long = pd.concat([long_na, long_mk]).sort_index()
long = long[~long.index.duplicated(keep="first")]
long.index = long.index.astype(str)
long.to_csv(DATA_DIR / "wfp_national_monthly_long.csv")
print(f"long series: {long.index.min()} to {long.index.max()}, {len(long)} months")

print(monthly[["egg_n_markets", "egg_median_price", "egg_rel_index", "chicken_median_price",
               "chicken_rel_index", "week", "use_for_calibration"]].round(3).to_string())
print(f"\nCalibration months: {len(out)} (excluded: {(~monthly['use_for_calibration']).sum()})")
print(f"2024 median nominal price  egg: {b['egg_median_price'].mean():,.0f}  "
      f"chicken: {b['chicken_median_price'].mean():,.0f} IDR/kg")
