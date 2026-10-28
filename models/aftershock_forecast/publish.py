"""Publish the trained aftershock model to Kaggle Models (private unless --public).

    python models/aftershock_forecast/publish.py OUT_DIR [--public]

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

SLUG = "indonesia-aftershock-forecast"
INSTANCE = "default"
DATASET = "https://www.kaggle.com/datasets/danielaijdkx/indonesia-earthquakes-usgs-daily"
STAGE_NAMES = {
    "at_mainshock/m45": "Right after the quake: M4.5+ aftershocks in 7 days",
    "at_mainshock/m5": "Right after the quake: M5+ aftershocks in 7 days",
    "after_24h/m45": "After 24 hours: M4.5+ aftershocks in days 2-7",
    "after_24h/m5": "After 24 hours: M5+ aftershocks in days 2-7",
}


def results_table(info):
    rows = ["| Forecast | Model | Poisson deviance (lower is better) | MAE | Productivity-law baseline: deviance | MAE |",
            "|---|---|---|---|---|---|"]
    for key, name in STAGE_NAMES.items():
        e = info["stages"][key]
        best, base = e["test"][e["chosen"]], e["test"]["productivity law"]
        rows.append(f"| {name} | {e['chosen']} | {best['mean_poisson_deviance']} | {best['MAE']} | "
                    f"{base['mean_poisson_deviance']} | {base['MAE']} |")
    return "\n".join(rows)


def chance_table(info):
    rows = ["| Forecast | Brier score: model | baseline | always the average rate | Quakes with an M5+ aftershock |",
            "|---|---|---|---|---|"]
    for key in ("at_mainshock/m5", "after_24h/m5"):
        e = info["stages"][key]
        best, base = e["test"][e["chosen"]], e["test"]["productivity law"]
        rows.append(f"| {STAGE_NAMES[key]} | {best['brier_any']} | {base['brier_any']} | "
                    f"{best['brier_any_climatology']} | {best['share_with_any']:.0%} |")
    return "\n".join(rows)


def calibration_table(info):
    rows = ["| Forecast chance of an M5+ aftershock | Quakes | Mean forecast | Observed |", "|---|---|---|---|"]
    for r in info["stages"]["at_mainshock/m5"]["test_calibration"]:
        rows.append(f"| {r['forecast']} | {r['quakes']} | {r['mean_forecast']:.0%} | {r['observed']:.0%} |")
    return "\n".join(rows)


def examples_table(info):
    rows = ["| Date | Magnitude | Province | Depth (km) | Forecast M4.5+ | Actual | Forecast chance of M5+ | Actual M5+ |",
            "|---|---|---|---|---|---|---|---|"]
    for e in info["examples"]:
        rows.append(f"| {e['time']} | {e['mag']} | {e['province']} | {e['depth_km']:.0f} | {e['expected_m45']:.1f} | "
                    f"{e['actual_m45_7d']} | {e['p_any_m5']:.0%} | {e['actual_m5_7d']} |")
    return "\n".join(rows)


def description(info):
    d = info["data"]
    return "\n".join([
        "# Model Summary",
        "",
        "Forecasts **how many aftershocks will follow a strong earthquake in Indonesia** in the next 7 days, "
        "and the **chance of an aftershock of magnitude 5 or more**, from what is known about the "
        "mainshock: its magnitude, depth, location and the activity nearby in the month before. A second "
        "version updates the forecast after 24 hours, using how many aftershocks have already occurred.",
        "",
        "It is a small, transparent statistical model in the tradition of aftershock forecasting "
        "(Reasenberg & Jones; the USGS's operational aftershock forecasts): count models (scikit-learn), "
        "trained on Indonesia's own catalogue since 1990.",
        "",
        "**Not an official warning.** For safety decisions follow BMKG (Indonesia's meteorology, "
        "climatology and geophysics agency). No model can predict *when* a damaging aftershock will happen; "
        "this one gives probabilities for the coming week, which is what aftershock forecasts can do.",
        "",
        "# Model Characteristics",
        "",
        "- Aftershocks: M4.5+ quakes within the rupture zone (radius from Wells & Coppersmith's rupture "
        "length, at least 75 km) in the 7 days after the mainshock.",
        "- Four count models: M4.5+ and M5+ aftershocks, right after the quake and after 24 hours. The "
        "chance of at least one M5+ aftershock is 1 - exp(-expected count).",
        "- For each, three candidates were compared on a validation period "
        f"({d['validation'][0]} to {d['validation'][1]}, trained on earlier quakes): the classic "
        "*productivity law* (expected count grows exponentially with magnitude), a Poisson regression on all "
        "inputs, and gradient-boosted trees with a Poisson loss. The test period was not used to choose.",
        "",
        "# Data Overview",
        "",
        f"Trained on the `aftershock_sequences` table of [Indonesia Earthquakes since 1900 (USGS, daily)]({DATASET}): "
        f"{d['quakes']:,} independent M5.5+ earthquakes nearest Indonesia, {d['first']} to {d['last']}. "
        "Quakes that followed a larger one nearby within 30 days were left out (they are aftershocks themselves).",
        "",
        "# Evaluation Results",
        "",
        f"Held-out test period: {d['test'][0]} to {d['test'][1]} ({d['test_quakes']} quakes), with models "
        "trained only on earlier quakes.",
        "",
        results_table(info),
        "",
        "Chance of at least one M5+ aftershock (Brier score, lower is better):",
        "",
        chance_table(info),
        "",
        "Calibration, right after the quake (test period): when the model says X%, how often did it happen?",
        "",
        calibration_table(info),
        "",
        "The largest quakes of the test period, with the final model's forecast (the final model was "
        "refitted on all quakes, including these):",
        "",
        examples_table(info),
        "",
        "Reading the results honestly: aftershock counts are very noisy (some M6+ quakes have none, others "
        "dozens), so even a good forecast has large errors on single quakes. What matters is that the "
        "probabilities are calibrated. The productivity law alone is already a strong baseline.",
        "",
        "The published files are refitted on all quakes, including the test period.",
    ])


USAGE = """# Model Format

A dict of four fitted scikit-learn models saved with joblib (`model.joblib`), keyed by
(stage, size) with stage "at_mainshock" or "after_24h" and size "m45" or "m5", plus
`features.py` (input preparation and `forecast()`) and `model_info.json` (metrics and examples).

# Model Inputs

One row per M5.5+ earthquake with: latitude, longitude, depth_km, mag, mag_type and prior_m45_30d
(M4.5+ quakes nearby in the 30 days before). For "after_24h", also aftershocks_m45_1d. The
`aftershock_sequences.csv` file of the Indonesia earthquakes dataset has all of them.

# Model Outputs

expected_m45 and expected_m5 (expected number of aftershocks) and p_any_m5 (chance of at least
one M5+ aftershock) over the next 7 days (or days 2-7 for "after_24h").

# Model Usage

```python
import sys, glob, joblib, pandas as pd
folder = glob.glob("/kaggle/input/indonesia-aftershock-forecast/**/model.joblib", recursive=True)[0].rsplit("/", 1)[0]
sys.path.append(folder)
from features import forecast

models = joblib.load(f"{folder}/model.joblib")
quake = pd.DataFrame([{"latitude": -8.3, "longitude": 116.4, "depth_km": 10, "mag": 6.9,
                       "mag_type": "mww", "prior_m45_30d": 2}])
forecast(models, quake)                     # right after the quake
quake["aftershocks_m45_1d"] = 5
forecast(models, quake, stage="after_24h")  # one day later
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
            "ownerSlug": owner, "slug": SLUG, "title": "Indonesia Aftershock Forecast (7 days)",
            "subtitle": "7-day aftershock counts and M5+ chance after a strong Indonesian earthquake",
            "isPrivate": not args.public, "description": description(info), "publishTime": "",
            "provenanceSources": DATASET,
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
        chosen = sorted({e["chosen"] for e in info["stages"].values()})
        instance_meta = {
            "ownerSlug": owner, "modelSlug": SLUG, "instanceSlug": INSTANCE, "framework": "scikitLearn",
            "overview": f"Count models ({', '.join(chosen)}) of aftershocks after M5.5+ Indonesian earthquakes.",
            "usage": USAGE, "licenseName": "Apache 2.0", "fineTunable": False,
            "trainingData": [DATASET], "modelInstanceType": "Unspecified",
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
