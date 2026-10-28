"""Inputs of the Indonesia aftershock forecast, and how to turn its outputs into numbers people use.

Two forecasts per M5.5+ earthquake, each a Poisson model of a count:
- "at_mainshock": right after the quake, the number of M4.5+ aftershocks in the next 7 days;
- "after_24h": a day later, the number in days 2-7, now also knowing how many came in the first 24 hours.
For each, a second model forecasts the number of M5+ aftershocks, whose chance of at least one is
1 - exp(-expected count).

Inputs come from the `aftershock_sequences` table of the Indonesia earthquakes dataset, or can be
written by hand for a new quake (see `forecast()`).
"""

import numpy as np
import pandas as pd

BASE_FEATURES = ["mag", "depth_km", "log_prior_m45_30d", "shallow", "intermediate", "moment_mag", "lat", "lon"]
FEATURES = {
    "at_mainshock": BASE_FEATURES,
    "after_24h": BASE_FEATURES + ["log_aftershocks_m45_1d"],
}
TARGETS = {
    ("at_mainshock", "m45"): "aftershocks_m45_7d",
    ("at_mainshock", "m5"): "aftershocks_m5_7d",
    ("after_24h", "m45"): "aftershocks_m45_2_7d",
    ("after_24h", "m5"): "aftershocks_m5_2_7d",
}


def prepare(seq):
    """Model inputs (and targets, when present) from aftershock_sequences rows."""
    df = seq.copy()
    out = pd.DataFrame(index=df.index)
    out["mag"] = df["mag"].astype(float)
    out["depth_km"] = df["depth_km"].astype(float).clip(0, 700)
    out["log_prior_m45_30d"] = np.log1p(df["prior_m45_30d"].astype(float))
    out["shallow"] = (out["depth_km"] < 70).astype(float)
    out["intermediate"] = ((out["depth_km"] >= 70) & (out["depth_km"] < 300)).astype(float)
    out["moment_mag"] = df["mag_type"].fillna("").str.lower().str.startswith("mw").astype(float)
    out["lat"] = df["latitude"].astype(float)
    out["lon"] = df["longitude"].astype(float)
    if "aftershocks_m45_1d" in df:
        out["log_aftershocks_m45_1d"] = np.log1p(df["aftershocks_m45_1d"].astype(float))
    if "aftershocks_m45_7d" in df:
        out["aftershocks_m45_7d"] = df["aftershocks_m45_7d"].astype(float)
        out["aftershocks_m5_7d"] = df["aftershocks_m5_7d"].astype(float)
        out["aftershocks_m45_2_7d"] = (df["aftershocks_m45_7d"] - df["aftershocks_m45_1d"]).astype(float)
        out["aftershocks_m5_2_7d"] = (df["aftershocks_m5_7d"] - df["aftershocks_m5_1d"]).astype(float)
    return out


class Columns:
    """A fitted model that picks its own input columns (so every candidate takes the full table)."""

    def __init__(self, columns, model):
        self.columns, self.model = list(columns), model

    def fit(self, X, y):
        self.model.fit(X[self.columns], y)
        return self

    def predict(self, X):
        return np.clip(self.model.predict(X[self.columns]), 1e-6, None)


def forecast(models, quakes, stage="at_mainshock"):
    """Expected M4.5+ and M5+ aftershocks and the chance of at least one M5+.

    models: the dict saved in model.joblib; quakes: rows with latitude, longitude, depth_km, mag,
    mag_type, prior_m45_30d (and aftershocks_m45_1d for stage "after_24h").
    """
    X = prepare(quakes)[FEATURES[stage]]
    m45 = models[(stage, "m45")].predict(X)
    m5 = models[(stage, "m5")].predict(X)
    return pd.DataFrame({
        "expected_m45": np.round(m45, 2),
        "expected_m5": np.round(m5, 3),
        "p_any_m5": np.round(1 - np.exp(-m5), 3),
    }, index=quakes.index)
