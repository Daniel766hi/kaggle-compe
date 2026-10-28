"""Train and evaluate the Indonesia aftershock forecast; write the files published to Kaggle Models.

    python models/aftershock_forecast/train.py DATA_DIR OUT_DIR

DATA_DIR holds aftershock_sequences.csv from the Indonesia earthquakes dataset. OUT_DIR receives
model.joblib (a dict of the six fitted models), model_info.json and features.py.

Which quakes: M5.5+ earthquakes nearest Indonesia since 1990 with a full week after them,
excluding those that followed a larger quake nearby within 30 days (they are aftershocks
themselves, and their own "aftershocks" belong to the larger quake's sequence).

Candidates, compared on an inner validation period (2012-2017, trained on 1990-2011):
- "productivity law" (baseline): magnitude only. Aftershock numbers growing exponentially with
  magnitude is the classic empirical law (a Poisson regression on magnitude for counts, a logistic
  regression on magnitude for the chance of an M5+ aftershock).
- "linear": Poisson regression (counts) or logistic regression (chance) on all inputs.
- "boosted trees": gradient boosting (Poisson loss for counts, log loss for the chance) on all inputs.
The best on validation (mean Poisson deviance for counts, log loss for the chance) is then tested
on the held-out period (2018 onward), trained on everything before it, and finally refitted on
all quakes.

Train with the scikit-learn version Kaggle notebooks run (1.6.1 in October 2026, found from a
failing notebook's traceback): pickled models from newer versions fail to load there.
"""

import json
import shutil
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression, PoissonRegressor
from sklearn.metrics import log_loss, mean_poisson_deviance
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))
from features import FEATURES, TARGETS, Columns, forecast, prepare  # noqa: E402

VALID_FROM, TEST_FROM = pd.Timestamp("2012-01-01"), pd.Timestamp("2018-01-01")
BASELINE = "productivity law"


def candidates(stage, size):
    feats = FEATURES[stage]
    if size == "any_m5":
        return {
            BASELINE: (["mag"], lambda: make_pipeline(StandardScaler(), LogisticRegression(C=1e6, max_iter=1000))),
            "linear": (feats, lambda: make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=1000))),
            "boosted trees": (feats, lambda: HistGradientBoostingClassifier(
                max_iter=200, learning_rate=0.03, max_depth=3, min_samples_leaf=40, random_state=0)),
        }
    return {
        BASELINE: (["mag"], lambda: make_pipeline(StandardScaler(), PoissonRegressor(alpha=0.0, max_iter=1000))),
        "linear": (feats, lambda: make_pipeline(StandardScaler(), PoissonRegressor(alpha=1e-3, max_iter=1000))),
        "boosted trees": (feats, lambda: HistGradientBoostingRegressor(
            loss="poisson", max_iter=300, learning_rate=0.03, max_depth=3, min_samples_leaf=40, random_state=0)),
    }


def fit(stage, size, name, rows, target):
    cols, make = candidates(stage, size)[name]
    return Columns(cols, make()).fit(rows[FEATURES[stage]], rows[target])


def count_scores(y, pred):
    y, pred = np.asarray(y, dtype=float), np.asarray(pred, dtype=float)
    return {"mean_poisson_deviance": round(float(mean_poisson_deviance(y, pred)), 3),
            "MAE": round(float(np.abs(y - pred).mean()), 3),
            "mean_actual": round(float(y.mean()), 3), "mean_forecast": round(float(pred.mean()), 3)}


def chance_scores(y, p, base_rate):
    """Log loss and Brier score, and the Brier score of always forecasting the training base rate."""
    y, p = np.asarray(y, dtype=int), np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return {"log_loss": round(float(log_loss(y, p, labels=[0, 1])), 4),
            "brier": round(float(((p - y) ** 2).mean()), 4),
            "brier_base_rate": round(float(((base_rate - y) ** 2).mean()), 4),
            "base_rate_train": round(float(base_rate), 3),
            "share_with_any": round(float(y.mean()), 3), "mean_forecast": round(float(p.mean()), 3)}


def calibration(y, p, bins=(0, 0.1, 0.25, 0.5, 0.75, 1.01)):
    """Forecast chance vs how often it happened, in probability bins."""
    y, p = np.asarray(y), np.asarray(p)
    rows = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (p >= lo) & (p < hi)
        if m.sum():
            rows.append({"forecast": f"{lo:.0%}-{min(hi, 1):.0%}", "quakes": int(m.sum()),
                         "mean_forecast": round(float(p[m].mean()), 3), "observed": round(float(y[m].mean()), 3)})
    return rows


def load(data_dir):
    seq = pd.read_csv(Path(data_dir) / "aftershock_sequences.csv", parse_dates=["time"])
    keep = (seq["country"] == "Indonesia") & seq["complete_7d"].astype(bool) & ~seq["prior_larger_30d"].astype(bool)
    seq = seq[keep].sort_values("time").reset_index(drop=True)
    X = prepare(seq)
    X["time"] = seq["time"]
    return seq, X


def main(data_dir, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    seq, X = load(data_dir)
    inner = X[X["time"] < VALID_FROM]
    valid = X[(X["time"] >= VALID_FROM) & (X["time"] < TEST_FROM)]
    before_test, test = X[X["time"] < TEST_FROM], X[X["time"] >= TEST_FROM]
    print(f"{len(X):,} independent M5.5+ quakes: inner train {len(inner)}, validation {len(valid)}, "
          f"test {len(test)} ({test['time'].min():%Y-%m-%d} to {test['time'].max():%Y-%m-%d})")

    info = {"stages": {}, "data": {
        "quakes": len(X), "first": f"{X['time'].min():%Y-%m-%d}", "last": f"{X['time'].max():%Y-%m-%d}",
        "validation": [f"{VALID_FROM:%Y-%m-%d}", f"{TEST_FROM - pd.Timedelta(days=1):%Y-%m-%d}"],
        "test": [f"{TEST_FROM:%Y-%m-%d}", f"{test['time'].max():%Y-%m-%d}"], "test_quakes": len(test)}}
    final = {}
    for (stage, size), target in TARGETS.items():
        is_chance = size == "any_m5"
        valid_scores = {}
        for name in candidates(stage, size):
            pred = fit(stage, size, name, inner, target).predict(valid)
            valid_scores[name] = (chance_scores(valid[target], pred, inner[target].mean()) if is_chance
                                  else count_scores(valid[target], pred))
        metric = "log_loss" if is_chance else "mean_poisson_deviance"
        best = min(valid_scores, key=lambda n: valid_scores[n][metric])
        test_scores, test_preds = {}, {}
        for name in {best, BASELINE}:
            pred = fit(stage, size, name, before_test, target).predict(test)
            test_preds[name] = pred
            test_scores[name] = (chance_scores(test[target], pred, before_test[target].mean()) if is_chance
                                 else count_scores(test[target], pred))
        final[(stage, size)] = fit(stage, size, best, X, target)
        entry = {"target": target, "chosen": best, "validation": valid_scores, "test": test_scores}
        if is_chance:
            entry["test_calibration"] = calibration(test[target], test_preds[best])
        info["stages"][f"{stage}/{size}"] = entry
        print(f"\n{stage} / {size}: chosen {best}")
        print(json.dumps({k: v for k, v in entry.items() if k != "validation"}, indent=1))

    # Worked examples from the test period, for the model card.
    examples = seq[seq["time"] >= TEST_FROM].nlargest(6, "mag")
    fc = forecast(final, examples)
    info["examples"] = [
        {"time": f"{r.time:%Y-%m-%d}", "mag": r.mag, "province": r.province, "depth_km": r.depth_km,
         "expected_m45": float(fc.loc[i, "expected_m45"]), "p_any_m5": float(fc.loc[i, "p_any_m5"]),
         "actual_m45_7d": int(r.aftershocks_m45_7d), "actual_m5_7d": int(r.aftershocks_m5_7d)}
        for i, r in examples.iterrows()]
    info["features"] = FEATURES
    info["sklearn_version"] = sklearn.__version__
    info["note"] = ("Examples are predicted by the final model, which was refitted on all quakes including "
                    "these; the test scores above come from models that never saw the test period.")
    joblib.dump(final, out_dir / "model.joblib")
    shutil.copy(Path(__file__).with_name("features.py"), out_dir / "features.py")
    (out_dir / "model_info.json").write_text(json.dumps(info, indent=2, default=str))
    print(f"wrote {out_dir}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
