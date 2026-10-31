"""Inputs of the Wikipedia attention-decay forecast, and how to turn its output into daily views.

The model forecasts, for each of the 7 days after an attention spike, how far daily views fall
relative to the spike day, as a log ratio: log(1 + views on day h) - log(1 + views on the spike day).
`forecast()` turns that into expected daily views and a 7-day total.

Inputs come from the `attention_spikes` table of the "What Indonesia Reads" dataset, or can be
written by hand for a new spike (views on the spike day and the 7 days before, rank, date, title).
"""

import numpy as np
import pandas as pd

HORIZONS = list(range(1, 8))
BEFORE = [f"views_m{k}" for k in range(7, 0, -1)]  # views_m7 ... views_m1
FEATURES = [
    "horizon", "log_views_d0", "log_baseline", "log_rise", "log_m1", "log_m1_vs_m2", "days_with_views_before",
    "spike_rank", "weekday", "month", "title_has_year", "title_is_list", "title_words",
]


def spike_features(spikes):
    """One row per spike: the features that do not depend on the horizon."""
    s = spikes
    d0 = s["views_d0"].astype(float)
    before = s[BEFORE].astype(float)
    baseline = before.mean(axis=1)
    title = s["title"] if "title" in s else s["article"].str.replace("_", " ", regex=False)
    when = pd.to_datetime(s["spike_date"])
    return pd.DataFrame({
        "log_views_d0": np.log1p(d0),
        "log_baseline": np.log1p(baseline),
        "log_rise": np.log1p(d0) - np.log1p(baseline),
        "log_m1": np.log1p(before["views_m1"]),
        "log_m1_vs_m2": np.log1p(before["views_m1"]) - np.log1p(before["views_m2"]),
        "days_with_views_before": (before > 0).sum(axis=1).astype(float),
        "spike_rank": s["spike_rank"].astype(float),
        "weekday": when.dt.weekday.astype(float),
        "month": when.dt.month.astype(float),
        "title_has_year": title.str.contains(r"\b(?:19|20)\d\d\b", regex=True).astype(float),
        "title_is_list": title.str.lower().str.startswith("daftar ").astype(float),
        "title_words": title.str.split().str.len().astype(float),
    }, index=s.index)


def long_rows(spikes):
    """One row per spike and horizon (1-7), with the target when the views after are known."""
    base = spike_features(spikes)
    rows = []
    for h in HORIZONS:
        part = base.copy()
        part["horizon"] = float(h)
        part["spike_index"] = spikes.index
        col = f"views_p{h}"
        if col in spikes:
            part["target"] = np.log1p(spikes[col].astype(float)) - np.log1p(spikes["views_d0"].astype(float))
        rows.append(part)
    return pd.concat(rows, ignore_index=True)


def forecast(model, spikes):
    """Expected views on each of the 7 days after the spike, and their total."""
    X = long_rows(spikes.drop(columns=[f"views_p{h}" for h in HORIZONS], errors="ignore"))
    ratio = model.predict(X[FEATURES])
    views = np.expm1(np.log1p(spikes.loc[X["spike_index"], "views_d0"].to_numpy(dtype=float)) + ratio).clip(0)
    out = pd.DataFrame({"spike_index": X["spike_index"], "horizon": X["horizon"].astype(int), "views": views})
    wide = out.pivot(index="spike_index", columns="horizon", values="views").round(0)
    wide.columns = [f"forecast_p{h}" for h in wide.columns]
    wide["forecast_next_7d"] = wide.sum(axis=1)
    wide.index.name = None
    return wide.loc[spikes.index]
