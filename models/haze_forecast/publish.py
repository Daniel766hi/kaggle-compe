"""Publish the trained haze model to Kaggle Models (private unless --public).

    python models/haze_forecast/publish.py OUT_DIR [--public]

OUT_DIR is the folder written by train.py. The model card is generated from model_info.json,
so the numbers on Kaggle always match the evaluation of the files being uploaded.
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from kaggle_pipeline import kaggle_sync  # noqa: E402

SLUG = "indonesia-haze-pm25-next-day"
INSTANCE = "default"
DATASETS = {
    "Indonesia Air Quality": "https://www.kaggle.com/datasets/danielaijdkx/indonesia-air-quality-hourly-pm25",
    "Indonesia Daily Weather": "https://www.kaggle.com/datasets/danielaijdkx/indonesia-daily-weather-31-cities",
    "Indonesia Fire Hotspots": "https://www.kaggle.com/datasets/danielaijdkx/indonesia-fire-hotspots-nasa-firms",
}


def metric_table(block):
    rows = ["| Method | MAE (µg/m³) | RMSE | Unhealthy-day alerts: precision | recall |", "|---|---|---|---|---|"]
    for name, s in block.items():
        if name == "rows":
            continue
        rows.append(f"| {name} | {s['MAE']} | {s['RMSE']} | {s['unhealthy_precision']:.0%} | {s['unhealthy_recall']:.0%} |")
    return "\n".join(rows)


def description(info):
    test = info["test"]
    m = test["metrics"]
    coef = list(info["coefficients"].items())[:6]
    return "\n".join([
        "# Model Summary",
        "",
        "Forecasts **tomorrow's daily mean PM2.5** (fine particulate air pollution, µg/m³) for 31 Indonesian "
        "cities from what is known at the end of today: recent PM2.5, satellite fire detections within 100 "
        "and 300 km, rain, wind, temperature, evapotranspiration and the season. Built to give an early warning "
        "of haze from forest and peat fires (*karhutla*).",
        "",
        "It is a small, transparent model: a ridge regression (scikit-learn) on the day-to-day change of "
        "log PM2.5. Every input's effect can be read from its coefficient.",
        "",
        "# Model Characteristics",
        "",
        "- Target: log(1 + PM2.5 tomorrow) - log(1 + PM2.5 today); `predict_next_day()` converts it back to µg/m³.",
        "- Predicting the *change* lets the model follow haze peaks above anything in its training data, "
        "which tree models cannot do (a gradient-boosting model on the PM2.5 level was tested and failed badly "
        "in the record 2026 season).",
        "- Choice of model: four candidates compared on an inner validation year (Jul 2024 - Jun 2025); the test "
        "period below was not used to choose.",
        "",
        "Largest coefficients (standardized inputs):",
        "",
        "| Input | Coefficient |",
        "|---|---|",
        *[f"| `{k}` | {v:+.3f} |" for k, v in coef],
        "",
        "High PM2.5 compared with the past week tends to fall back (mean reversion); rain lowers it; fires "
        "within 100 km today raise it.",
        "",
        "# Data Overview",
        "",
        "Trained on these Kaggle datasets (all updated daily):",
        "",
        *[f"- [{name}]({url})" for name, url in DATASETS.items()],
        "",
        f"Training rows: city-days from {info['trained_on'][0]} to {info['trained_on'][1]}.",
        "",
        "**Important:** the PM2.5 values are estimates from the CAMS atmospheric model (via Open-Meteo), not "
        "ground-station measurements. The model therefore forecasts the CAMS estimate. CAMS uses satellite fire "
        "data itself, so the fire inputs partly overlap with how the target was made.",
        "",
        "# Evaluation Results",
        "",
        f"Held-out test period {test['period'][0]} to {test['period'][1]} (trained on earlier data only), "
        "including the record 2026 fire season. Compared with two simple baselines.",
        "",
        f"**All cities** ({m['all cities']['rows']:,} city-days):",
        "",
        metric_table(m["all cities"]),
        "",
        f"**Fire-belt cities (Pekanbaru, Palembang, Jambi, Palangka Raya, Pontianak, Banjarmasin), "
        f"August-October** ({m['fire-belt cities, Aug-Oct']['rows']:,} city-days):",
        "",
        metric_table(m["fire-belt cities, Aug-Oct"]),
        "",
        "Reading the results honestly: tomorrow's air is usually close to today's, so \"tomorrow = today\" is "
        "a strong baseline. The model improves on it modestly (lower error, and fewer false alarms when it "
        "predicts an unhealthy day, above 55.5 µg/m³), but catches slightly fewer unhealthy days. It is a "
        "transparent baseline for haze forecasting, not a replacement for official forecasts.",
        "",
        "The published files are refitted on all data, including the test period.",
    ])


USAGE = """# Model Format

scikit-learn pipeline saved with joblib (`model.joblib`), plus `features.py` (feature builder and
`predict_next_day`) and `model_info.json` (features, metrics, coefficients).

# Model Inputs

Build the inputs with `features.build_features(aq, weather, hotspots, cities)` from the three datasets:
`idn_air_quality_daily.csv` and `cities.csv`, `idn_weather_daily.csv`, `hotspots.parquet`.

# Model Outputs

Tomorrow's daily mean PM2.5 in µg/m³ for each city-day row.

# Model Usage

```python
import sys, joblib, pandas as pd
sys.path.append("/kaggle/input/indonesia-haze-pm25-next-day/scikitlearn/default/1")  # folder with these files
from features import build_features, predict_next_day

model = joblib.load(".../model.joblib")
X = build_features(aq, weather, hotspots, cities)          # DataFrames read from the datasets
latest = X[X["date"] == X["date"].max()].dropna(subset=["pm25"])
latest["pm25_tomorrow"] = predict_next_day(model, latest)
```

`joblib.load` unpickles the file: only load model files from sources you trust.

# Changelog

Version 1: first release.
"""


def main():
    p = argparse.ArgumentParser()
    p.add_argument("out_dir")
    p.add_argument("--public", action="store_true")
    args = p.parse_args()
    owner = os.environ.get("KAGGLE_USERNAME") or sys.exit("Set KAGGLE_USERNAME")
    out_dir = Path(args.out_dir)
    info = json.loads((out_dir / "model_info.json").read_text())
    api = kaggle_sync.get_api()

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        try:
            api.model_get(f"{owner}/{SLUG}")
            exists = True
        except Exception:  # noqa: BLE001 - not found
            exists = False
        model_meta = {
            "ownerSlug": owner, "slug": SLUG, "title": "Indonesia Haze: Next-Day PM2.5 Forecast",
            "subtitle": "Forecast tomorrow's PM2.5 in 31 Indonesian cities from fires, weather and air quality",
            "isPrivate": not args.public, "description": description(info), "publishTime": "",
            "provenanceSources": ", ".join(DATASETS.values()),
        }
        (tmp / "model-metadata.json").write_text(json.dumps(model_meta, indent=2))
        if exists:
            api.model_update(str(tmp))
            print("model card updated")
        else:
            print(api.model_create_new(str(tmp)))

        files = tmp / "files"
        files.mkdir()
        for name in ("model.joblib", "features.py", "model_info.json"):
            shutil.copy(out_dir / name, files / name)
        instance_meta = {
            "ownerSlug": owner, "modelSlug": SLUG, "instanceSlug": INSTANCE, "framework": "scikitLearn",
            "overview": "Ridge regression on the daily change of log PM2.5; inputs from three Kaggle datasets.",
            "usage": USAGE, "licenseName": "Apache 2.0", "fineTunable": False,
            "trainingData": list(DATASETS.values()), "modelInstanceType": "Unspecified",
            "baseModelInstanceId": 0, "externalBaseModelUrl": "",
        }
        (files / "model-instance-metadata.json").write_text(json.dumps(instance_meta, indent=2))
        try:
            print(api.model_instance_create(str(files), quiet=True))
        except Exception as exc:  # noqa: BLE001 - instance exists: upload a new version
            print(f"instance exists ({exc}); creating a new version")
            (files / "model-instance-metadata.json").unlink()
            print(api.model_instance_version_create(f"{owner}/{SLUG}/scikitLearn/{INSTANCE}", str(files),
                                                    version_notes="Retrained", quiet=True))


if __name__ == "__main__":
    main()
