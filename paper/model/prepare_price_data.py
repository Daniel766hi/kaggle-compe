"""Convert raw price data (e.g. downloaded from Panel Harga Pangan) into data/historical_prices.csv.

Input CSV needs columns:  date, egg_price, chicken_price   (Rp/kg, any frequency, national average)
Output: weekly series indexed by model week (0 = first week of 2024), as prices relative to the
2024 average (the model's baseline), used by s02_validation.py for calibration and fit statistics.

Usage:  python prepare_price_data.py path/to/raw_prices.csv
"""
import sys

import pandas as pd

from common import DATA_DIR

raw = pd.read_csv(sys.argv[1], parse_dates=["date"]).sort_values("date")
raw = raw.set_index("date")[["egg_price", "chicken_price"]].resample("W-MON").mean().interpolate()
base = raw.loc["2024"].mean()
out = pd.DataFrame({
    "week": ((raw.index - pd.Timestamp("2024-01-01")).days // 7).astype(int),
    "rel_egg_price": (raw["egg_price"] / base["egg_price"]).values,
    "rel_chicken_price": (raw["chicken_price"] / base["chicken_price"]).values,
})
out = out[(out["week"] >= 0) & (out["week"] <= 312)]
out.to_csv(DATA_DIR / "historical_prices.csv", index=False)
print(f"wrote {len(out)} weeks to {DATA_DIR / 'historical_prices.csv'}")
print("Baseline 2024 mean prices (Rp/kg) -> put these in the .mdl as Baseline egg/chicken price:")
print(base.round(0).to_string())
