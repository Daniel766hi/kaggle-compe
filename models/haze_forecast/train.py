"""Train and evaluate the next-day PM2.5 model; write the artifacts published to Kaggle Models.

    python models/haze_forecast/train.py DATA_DIR OUT_DIR

DATA_DIR holds idn_air_quality_daily.csv, cities.csv, idn_weather_daily.csv and hotspots.parquet
(the current versions of the three Kaggle datasets). OUT_DIR receives model.joblib,
model_info.json and features.py.

Model choice: four candidates (gradient boosting on the PM2.5 level, gradient boosting and a
ridge regression on the day-to-day change) were compared on an inner validation year
(Jul 2024 - Jun 2025, trained on earlier data). The ridge regression on the log change was best
there and is used here. The held-out test period (from Jul 2025, including the 2026 fire season)
was not used for that choice.
"""

import json
import shutil
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))
from features import FEATURES, LOG_FEATURES, build_features, predict_next_day  # noqa: E402

TEST_FROM = pd.Timestamp("2025-07-01")  # held out: includes the 2026 fire season
UNHEALTHY = 55.5  # µg/m³: US EPA "unhealthy" 24-hour PM2.5 level
FIRE_BELT = ["Pekanbaru", "Palembang", "Jambi", "Palangka Raya", "Pontianak", "Banjarmasin"]


def make_model():
    other = [f for f in FEATURES if f not in LOG_FEATURES]
    prep = ColumnTransformer([("log", FunctionTransformer(np.log1p, feature_names_out="one-to-one"), LOG_FEATURES),
                              ("raw", "passthrough", other)])
    return make_pipeline(prep, SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=1.0))


def fit(rows):
    change = np.log1p(rows["target"]) - np.log1p(rows["pm25"])
    return make_model().fit(rows[FEATURES], change)


def scores(y, pred):
    y, pred = np.asarray(y), np.asarray(pred)
    hit, flag = y >= UNHEALTHY, pred >= UNHEALTHY
    return {
        "MAE": round(float(np.abs(pred - y).mean()), 2),
        "RMSE": round(float(np.sqrt(((pred - y) ** 2).mean())), 2),
        "unhealthy_days": int(hit.sum()),
        "unhealthy_recall": round(float((flag & hit).sum() / hit.sum()), 3) if hit.sum() else None,
        "unhealthy_precision": round(float((flag & hit).sum() / flag.sum()), 3) if flag.sum() else None,
    }


def evaluate(test, pred):
    """Model vs two baselines: tomorrow = today (persistence), tomorrow = last 7 days' mean."""
    subsets = {
        "all cities": test.index,
        "fire-belt cities, Aug-Oct": test.index[test["city"].isin(FIRE_BELT) & test["date"].dt.month.isin([8, 9, 10])],
    }
    out = {}
    for name, idx in subsets.items():
        t = test.loc[idx]
        out[name] = {
            "rows": len(t),
            "model": scores(t["target"], pred.loc[idx]),
            "persistence (tomorrow = today)": scores(t["target"], t["pm25"]),
            "7-day mean": scores(t["target"], t["pm25_mean7"]),
        }
    return out


def coefficients(model):
    names = model[0].get_feature_names_out()
    names = [n.split("__", 1)[1] for n in names]
    return pd.Series(model[-1].coef_, index=names).sort_values(key=abs, ascending=False).round(4)


def main(data_dir, out_dir):
    data_dir, out_dir = Path(data_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    aq = pd.read_csv(data_dir / "idn_air_quality_daily.csv", parse_dates=["date"])
    cities = pd.read_csv(data_dir / "cities.csv")
    weather = pd.read_csv(data_dir / "idn_weather_daily.csv", parse_dates=["date"])
    weather = weather[weather["date"] >= aq["date"].min() - pd.Timedelta(days=30)]
    hotspots = pd.read_parquet(data_dir / "hotspots.parquet", columns=["acq_date", "latitude", "longitude"])

    df = build_features(aq, weather, hotspots, cities)
    usable = df.dropna(subset=["target", "pm25", "pm25_lag1", "pm25_mean7"])
    train, test = usable[usable["date"] < TEST_FROM], usable[usable["date"] >= TEST_FROM]
    print(f"train {len(train):,} rows ({train['date'].min():%Y-%m-%d} to {train['date'].max():%Y-%m-%d}), "
          f"test {len(test):,} rows ({test['date'].min():%Y-%m-%d} to {test['date'].max():%Y-%m-%d})")

    model = fit(train)
    pred = pd.Series(predict_next_day(model, test), index=test.index)
    metrics = evaluate(test, pred)
    print(json.dumps(metrics, indent=2))

    # The published model is refitted on everything, including the test period.
    final = fit(usable)
    coef = coefficients(final)
    print("Coefficients (standardized inputs; target = log change of PM2.5):")
    print(coef.to_string())
    joblib.dump(final, out_dir / "model.joblib")
    shutil.copy(Path(__file__).with_name("features.py"), out_dir / "features.py")
    info = {
        "features": FEATURES,
        "log_features": LOG_FEATURES,
        "cities": sorted(cities["city"]),
        "trained_on": [f"{usable['date'].min():%Y-%m-%d}", f"{usable['date'].max():%Y-%m-%d}"],
        "test": {"period": [f"{TEST_FROM:%Y-%m-%d}", f"{test['date'].max():%Y-%m-%d}"], "metrics": metrics},
        "coefficients": coef.to_dict(),
        "target": "next day's mean PM2.5 (µg/m³), as estimated by CAMS via Open-Meteo",
        "unhealthy_threshold": UNHEALTHY,
    }
    (out_dir / "model_info.json").write_text(json.dumps(info, indent=2))
    print(f"wrote {out_dir}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
