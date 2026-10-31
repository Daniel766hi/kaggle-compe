"""Train and evaluate the Wikipedia attention-decay forecast; write the files published to Kaggle Models.

    python models/attention_decay/train.py DATA_DIR OUT_DIR

DATA_DIR holds attention_spikes.csv from the "What Indonesia Reads" dataset. OUT_DIR receives
model.joblib, model_info.json and features.py.

The spikes are split by date: the oldest 65% train, the next 15% validate (to choose the model),
the newest 20% test. Candidates:
- "persistence" (baseline): views stay at the spike-day level.
- "typical decay" (baseline): every spike follows the median decay curve of the training spikes.
- "linear": ridge regression on the inputs.
- "boosted trees": gradient boosting on the inputs (squared error), and "boosted trees (median)", the
  same fitted to absolute error.
The best on validation is tested, then refitted on all spikes for publishing.

Train with the scikit-learn version Kaggle notebooks run (1.6.1 in October 2026): pickled models
from newer versions fail to load there.
"""

import json
import shutil
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))
from features import FEATURES, HORIZONS, forecast, long_rows  # noqa: E402


class TypicalDecay:
    """Baseline: the median log ratio of each horizon in the training data."""

    def fit(self, X, y):
        self.by_h = pd.Series(np.asarray(y)).groupby(np.asarray(X["horizon"])).median().to_dict()
        return self

    def predict(self, X):
        return np.array([self.by_h[h] for h in X["horizon"]])


class Persistence:
    def fit(self, X, y):
        return self

    def predict(self, X):
        return np.zeros(len(X))


CANDIDATES = {
    "persistence": Persistence,
    "typical decay": TypicalDecay,
    "linear": lambda: make_pipeline(StandardScaler(), Ridge(alpha=1.0)),
    "boosted trees": lambda: HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05, max_depth=6,
                                                           min_samples_leaf=50, random_state=0),
    # The same trees fitted to the median (absolute error) instead of the mean: attention decays are
    # skewed, and the scores below are absolute errors.
    "boosted trees (median)": lambda: HistGradientBoostingRegressor(
        loss="absolute_error", max_iter=400, learning_rate=0.05, max_depth=6, min_samples_leaf=50, random_state=0),
}
BASELINES = ("persistence", "typical decay")


def scores(spikes, X, pred):
    """Errors on the log scale per horizon, and on the 7-day total."""
    err = np.abs(np.asarray(pred) - X["target"].to_numpy())
    by_h = {int(h): round(float(e), 3) for h, e in pd.Series(err).groupby(X["horizon"].to_numpy()).mean().items()}
    d0 = spikes.loc[X["spike_index"], "views_d0"].to_numpy(dtype=float)
    views = np.expm1(np.log1p(d0) + np.asarray(pred)).clip(0)
    total = pd.Series(views).groupby(X["spike_index"].to_numpy()).sum()
    actual = spikes.loc[total.index, "next_7d"].astype(float)
    ape = (np.abs(total.to_numpy() - actual.to_numpy()) / actual.clip(lower=1).to_numpy())
    return {
        "mae_log_by_horizon": by_h,
        "mae_log": round(float(err.mean()), 3),
        "next_7d_median_ape": round(float(np.median(ape)), 3),
        "next_7d_wape": round(float(np.abs(total.to_numpy() - actual.to_numpy()).sum() / actual.sum()), 3),
        "next_7d_within_25pct": round(float((ape <= 0.25).mean()), 3),
    }


def main(data_dir, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    spikes = pd.read_csv(Path(data_dir) / "attention_spikes.csv", parse_dates=["spike_date"])
    # One-day bursts (next-day views below 1% of the spike day) are almost always automated traffic.
    bursts = spikes["one_day_burst"].astype(bool) if "one_day_burst" in spikes else False
    spikes = spikes[(spikes["views_d0"] > 0) & ~bursts].sort_values("spike_date").reset_index(drop=True)
    cut_valid, cut_test = spikes["spike_date"].quantile([0.65, 0.80])
    parts = {"train": spikes[spikes["spike_date"] < cut_valid],
             "valid": spikes[(spikes["spike_date"] >= cut_valid) & (spikes["spike_date"] < cut_test)],
             "test": spikes[spikes["spike_date"] >= cut_test]}
    rows = {k: long_rows(v) for k, v in parts.items()}
    before_test = pd.concat([rows["train"], rows["valid"]], ignore_index=True)
    for k, v in parts.items():
        print(f"{k}: {len(v):,} spikes, {v['spike_date'].min():%Y-%m-%d} to {v['spike_date'].max():%Y-%m-%d}")

    valid_scores = {}
    for name, make in CANDIDATES.items():
        model = make().fit(rows["train"][FEATURES], rows["train"]["target"])
        valid_scores[name] = scores(spikes, rows["valid"], model.predict(rows["valid"][FEATURES]))
    best = min(valid_scores, key=lambda n: valid_scores[n]["mae_log"])
    test_scores = {}
    for name in dict.fromkeys([best, *BASELINES]):
        model = CANDIDATES[name]().fit(before_test[FEATURES], before_test["target"])
        test_scores[name] = scores(spikes, rows["test"], model.predict(rows["test"][FEATURES]))
    print(f"chosen on validation: {best}")
    print(json.dumps({"validation": {n: {k: v for k, v in s.items() if k != 'mae_log_by_horizon'}
                                     for n, s in valid_scores.items()}, "test": test_scores}, indent=1))

    all_rows = long_rows(spikes)
    final = CANDIDATES[best]().fit(all_rows[FEATURES], all_rows["target"])
    test_spikes = parts["test"]
    typical = pd.Series(np.asarray(all_rows["target"])).groupby(all_rows["horizon"].to_numpy()).median()
    examples = test_spikes.nlargest(8, "views_d0")
    fc = forecast(final, examples)
    info = {
        "data": {"spikes": len(spikes), "first": f"{spikes['spike_date'].min():%Y-%m-%d}",
                 "last": f"{spikes['spike_date'].max():%Y-%m-%d}",
                 **{f"{k}_period": [f"{v['spike_date'].min():%Y-%m-%d}", f"{v['spike_date'].max():%Y-%m-%d}"]
                    for k, v in parts.items()},
                 **{f"{k}_spikes": len(v) for k, v in parts.items()}},
        "chosen": best, "validation": valid_scores, "test": test_scores,
        "typical_decay_share_of_spike_day": {int(h): round(float(np.expm1(r) + 1), 3) for h, r in typical.items()},
        "examples": [{"date": f"{r.spike_date:%Y-%m-%d}", "title": r.title, "views_d0": int(r.views_d0),
                      "forecast_next_7d": int(fc.loc[i, "forecast_next_7d"]), "actual_next_7d": int(r.next_7d)}
                     for i, r in examples.iterrows()],
        "features": FEATURES, "horizons": HORIZONS, "sklearn_version": sklearn.__version__,
        "note": "Examples use the final model, refitted on all spikes including these; test scores come "
                "from models trained only on earlier spikes.",
    }
    joblib.dump(final, out_dir / "model.joblib")
    shutil.copy(Path(__file__).with_name("features.py"), out_dir / "features.py")
    (out_dir / "model_info.json").write_text(json.dumps(info, indent=2))
    print(f"wrote {out_dir}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
