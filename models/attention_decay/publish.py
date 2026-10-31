"""Publish the trained attention-decay model to Kaggle Models (private unless --public).

    python models/attention_decay/publish.py OUT_DIR [--public] [--notes "..."]

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

SLUG = "wikipedia-attention-decay-forecast"
INSTANCE = "default"
DATASET = "https://www.kaggle.com/datasets/danielaijdkx/indonesian-wikipedia-daily-top-articles"


def results_table(info):
    rows = ["| Method | Error on log scale (MAE) | 7-day total: median error | Weighted error (WAPE) | Within 25% |",
            "|---|---|---|---|---|"]
    for name, s in info["test"].items():
        label = f"**{name}** (chosen)" if name == info["chosen"] else name
        rows.append(f"| {label} | {s['mae_log']} | {s['next_7d_median_ape']:.0%} | {s['next_7d_wape']:.0%} | "
                    f"{s['next_7d_within_25pct']:.0%} |")
    return "\n".join(rows)


def horizon_table(info):
    names = list(info["test"])
    rows = ["| Days after the spike | " + " | ".join(names) + " |", "|---" * (len(names) + 1) + "|"]
    for h in info["horizons"]:
        rows.append(f"| {h} | " + " | ".join(str(info["test"][n]["mae_log_by_horizon"][str(h)]) for n in names) + " |")
    return "\n".join(rows)


def decay_table(info):
    share = info["typical_decay_share_of_spike_day"]
    return ("| Day after the spike | " + " | ".join(share) + " |\n|---" + "|---" * len(share) + "|\n"
            "| Typical views, as a share of the spike day | " + " | ".join(f"{v:.0%}" for v in share.values()) + " |")


def examples_table(info):
    rows = ["| Spike day | Article | Views on the spike day | Forecast, next 7 days | Actual |", "|---|---|---|---|---|"]
    for e in info["examples"]:
        rows.append(f"| {e['date']} | {e['title']} | {e['views_d0']:,} | {e['forecast_next_7d']:,} | {e['actual_next_7d']:,} |")
    return "\n".join(rows)


def honest_reading(info):
    """The 'reading the results' paragraph, written from the numbers so it never overstates them."""
    best, base = info["test"][info["chosen"]], info["test"]["typical decay"]
    lines = ["Reading the results honestly:", ""]
    lines.append("- Attention after a spike fades fast and in a fairly typical way, so the \"typical decay\" rule is "
                 "a strong baseline and \"views stay the same\" is far off.")
    wins = [label for key, label in (("mae_log", "daily error (log scale)"), ("next_7d_wape", "weighted 7-day error"),
                                     ("next_7d_median_ape", "median 7-day error"))
            if best[key] < base[key]]
    losses = [label for key, label in (("mae_log", "daily error (log scale)"), ("next_7d_wape", "weighted 7-day error"),
                                       ("next_7d_median_ape", "median 7-day error"))
              if best[key] > base[key]]
    if wins:
        lines.append(f"- The model beats the typical decay on {' and '.join(wins)}" +
                     (f", but not on {' and '.join(losses)}." if losses else "."))
    else:
        lines.append("- The model did not beat the typical decay on the test period: use the typical curve.")
    lines.append(f"- Errors on single spikes are large: only {best['next_7d_within_25pct']:.0%} of 7-day totals were "
                 "within 25%. A story that develops (a second event, an announcement) restarts the attention, "
                 "and page views alone cannot see that coming.")
    lines.append("- Spikes whose views vanish the next day (`one_day_burst`, almost always automated traffic) were "
                 "left out of training and testing.")
    return lines


def description(info):
    d = info["data"]
    return "\n".join([
        "# Model Summary",
        "",
        "When an Indonesian Wikipedia article suddenly jumps into the day's top 100 (a news event, a death, "
        "a match, a viral topic), **how many views will it get over the next week?** This model forecasts the "
        "daily views for each of the 7 days after such an *attention spike*, from the spike day and the week "
        "before it.",
        "",
        "It is a demand-shock forecast: the same question as \"how fast does demand return to normal after a "
        "promotion or a news shock?\", on a free, daily, public signal of attention.",
        "",
        "# Model Characteristics",
        "",
        "- Target: for each day h = 1..7 after the spike, log(1 + views on day h) - log(1 + views on the spike "
        "day). `forecast()` turns this into daily views and a 7-day total.",
        "- Inputs: views on the spike day and on each of the 7 days before, the spike's rank, weekday and "
        "month, and simple title features (contains a year, is a list, number of words).",
        f"- Candidates: two baselines (views stay at the spike level; every spike follows the typical decay "
        f"curve) and two models (ridge regression, gradient-boosted trees), compared on a validation period "
        f"({d['valid_period'][0]} to {d['valid_period'][1]}). Chosen: **{info['chosen']}**.",
        "",
        "The typical decay curve, from all spikes:",
        "",
        decay_table(info),
        "",
        "# Data Overview",
        "",
        f"Trained on the `attention_spikes` table of [What Indonesia Reads: Wikipedia Top 1000 Daily]({DATASET}): "
        f"{d['spikes']:,} spikes from {d['first']} to {d['last']}. A spike is an article that entered the "
        "day's top 100 after being outside the top 1,000 on each of the 7 days before.",
        "",
        "# Evaluation Results",
        "",
        f"Held-out test period: the newest spikes, {d['test_period'][0]} to {d['test_period'][1]} "
        f"({d['test_spikes']:,} spikes), with models trained only on earlier spikes.",
        "",
        results_table(info),
        "",
        "Error on the log scale by day after the spike (0.1 is about a 10% error):",
        "",
        horizon_table(info),
        "",
        "The biggest spikes of the test period, with the final model's forecast (the final model was refitted "
        "on all spikes, including these):",
        "",
        examples_table(info),
        "",
        *honest_reading(info),
        "",
        "The published file is refitted on all spikes, including the test period.",
    ])


USAGE = """# Model Format

A scikit-learn model saved with joblib (`model.joblib`), plus `features.py` (input preparation and
`forecast()`) and `model_info.json` (metrics and examples). Trained with scikit-learn
{sklearn_version}, the version Kaggle notebooks run; other versions may fail to load the file.

# Model Inputs

One row per spike with: views_m7 ... views_m1 (views on each of the 7 days before), views_d0
(views on the spike day), spike_rank, spike_date and title (or article). The `attention_spikes.csv`
file of the dataset has all of them.

# Model Outputs

forecast_p1 ... forecast_p7 (expected views on each of the 7 days after) and forecast_next_7d.

# Model Usage

```python
import sys, glob, joblib, pandas as pd
folder = glob.glob("/kaggle/input/wikipedia-attention-decay-forecast/**/model.joblib", recursive=True)[0].rsplit("/", 1)[0]
sys.path.append(folder)
from features import forecast

model = joblib.load(f"{folder}/model.joblib")
spike = pd.DataFrame([{"title": "Gempa bumi Cianjur 2022", "spike_date": "2022-11-21", "spike_rank": 2,
                       "views_d0": 150000, **{f"views_m{k}": 0 for k in range(1, 8)}}])
forecast(model, spike)
```

`joblib.load` unpickles the file: only load model files from sources you trust.

# Changelog

Version 1: first release.
"""


def main():
    p = argparse.ArgumentParser()
    p.add_argument("out_dir")
    p.add_argument("--public", action="store_true")
    p.add_argument("--notes", default="Retrained", help="version notes when the instance already exists")
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
            "ownerSlug": owner, "slug": SLUG, "title": "Wikipedia Attention Decay Forecast (Indonesia)",
            "subtitle": "How many views a spiking Indonesian Wikipedia article gets over the next 7 days",
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
        instance_meta = {
            "ownerSlug": owner, "modelSlug": SLUG, "instanceSlug": INSTANCE, "framework": "scikitLearn",
            "overview": f"{info['chosen'].capitalize()} forecasting daily views for 7 days after a Wikipedia attention spike.",
            "usage": USAGE.replace("{sklearn_version}", info.get("sklearn_version", "1.6.1")),
            "licenseName": "Apache 2.0", "fineTunable": False, "trainingData": [DATASET],
            "modelInstanceType": "Unspecified", "baseModelInstanceId": 0, "externalBaseModelUrl": "",
        }
        (files / "model-instance-metadata.json").write_text(json.dumps(instance_meta, indent=2))
        resp = api.model_instance_create(str(files), quiet=True)
        print(resp)
        if getattr(resp, "error_code", None) == 409 or "already used" in str(getattr(resp, "error", "") or ""):
            print("instance exists; updating its card and uploading a new version")
            api.model_instance_update(str(files))
            (files / "model-instance-metadata.json").unlink()
            print(api.model_instance_version_create(f"{owner}/{SLUG}/scikitLearn/{INSTANCE}", str(files),
                                                    version_notes=args.notes, quiet=True))


if __name__ == "__main__":
    main()
