"""Shared configuration and helpers for the MBG poultry SD + ML pipeline.

Every number in UNCERTAINTIES, POLICIES and in mbg_poultry.mdl is a PLACEHOLDER
until you replace it with values justified from data, literature or interviews.
While DEMO is True, every figure and table is stamped as demo output.
"""
from __future__ import annotations

import os
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

HERE = Path(__file__).resolve().parent
MODEL_FILE = HERE / "mbg_poultry.mdl"
DATA_DIR = HERE / "data"

# Set to False only after every parameter and range has been justified/calibrated.
DEMO = True
OUT_DIR = HERE / ("outputs_demo" if DEMO else "outputs")
OUT_DIR.mkdir(exist_ok=True)

DEMO_STAMP = "DEMO OUTPUT - PLACEHOLDER PARAMETERS - NOT RESEARCH RESULTS"

# --------------------------------------------------------------------- uncertainties
# name in model: (low, high).  Justify every range in the paper (Table: uncertainties).
UNCERTAINTIES: dict[str, tuple[float, float]] = {
    "Rollout duration": (52, 104),
    "Egg per beneficiary": (0.05, 0.15),
    "Chicken per beneficiary": (0.08, 0.22),
    "Price expectation delay": (4, 16),
    "Investment sensitivity": (0.5, 3.0),
    "Supply line weight": (0.1, 1.0),
    "Hatchery capacity factor": (1.1, 2.0),
    "DOC capacity factor": (1.05, 1.6),
    "Household egg elasticity": (-1.0, -0.3),
    "Household chicken elasticity": (-1.2, -0.4),
    "Price sensitivity to coverage": (0.5, 2.0),
    "Feed shock magnitude": (0.0, 0.5),
    "Outbreak loss fraction": (0.0, 0.3),
    "Base suspension fraction": (0.0005, 0.005),
    "Strain sensitivity": (0.0, 5.0),
    "Intermediary margin": (0.05, 0.30),
    "Maximum relative price": (2.0, 4.0),
}

# --------------------------------------------------------------------- policies
# Each policy maps a sampled scenario (dict) to the parameters actually run.
BASE_LEVERS = {"Cooperative sourcing share": 0.1, "Forward contract share": 0.0,
               "Menu flexibility switch": 0}


def _policy(name, levers=None, rollout_mult=1.0):
    def apply(scn: dict) -> dict:
        p = dict(scn)
        p.update(BASE_LEVERS)
        if levers:
            p.update(levers)
        p["Rollout duration"] = scn["Rollout duration"] * rollout_mult
        return p
    apply.__name__ = name
    return apply


POLICIES = {
    "P0 Baseline": _policy("P0"),
    "P1 Phased roll-out": _policy("P1", rollout_mult=1.75),
    "P2 Cooperative sourcing": _policy("P2", {"Cooperative sourcing share": 0.6}),
    "P3 Forward contracts": _policy("P3", {"Forward contract share": 0.8}),
    "P4 Menu flexibility": _policy("P4", {"Menu flexibility switch": 1}),
    "P5 Combined (P2+P3+P4)": _policy("P5", {"Cooperative sourcing share": 0.6,
                                             "Forward contract share": 0.8,
                                             "Menu flexibility switch": 1}),
}

# --------------------------------------------------------------------- outcomes
SPIKE_THRESHOLD = 0.10      # programme-attributable price rise > +10 percentage points = "spike" (justify in paper)
EARLY_WARNING_WEEK = 65     # observables read 13 weeks after programme start
PROGRAMME_START = 52

RETURN_COLS = [
    "Relative egg price", "Relative chicken price", "Programme coverage",
    "Household egg consumption ratio", "Household chicken consumption ratio",
    "Egg farmer margin", "Protein cost per portion", "Laying hens", "Pullets",
    "Pullet placement", "Relative egg coverage", "Relative chicken coverage",
    "Kitchen opening rate", "Suspended kitchens", "Operational kitchens",
    "MBG egg demand", "MBG chicken demand", "Egg production", "Chicken production",
    "Relative feed price", "DOC placement",
]

OUTCOMES = ["peak_egg_price", "peak_chicken_price", "weeks_egg_above_thr",
            "weeks_chicken_above_thr", "hh_egg_loss", "hh_chicken_loss",
            "egg_margin_volatility", "mean_cost_per_portion", "mean_coverage_last52"]
OUTCOME_LABELS = {
    "peak_egg_price": "Peak programme-attributable egg price rise",
    "peak_chicken_price": "Peak programme-attributable chicken price rise",
    "weeks_egg_above_thr": "Weeks egg price excess > threshold",
    "weeks_chicken_above_thr": "Weeks chicken price excess > threshold",
    "hh_egg_loss": "Mean household egg consumption loss",
    "hh_chicken_loss": "Mean household chicken consumption loss",
    "egg_margin_volatility": "Egg farmer margin volatility (SD)",
    "mean_cost_per_portion": "Protein cost per portion (Rp)",
    "mean_coverage_last52": "Programme coverage, final year",
}

OBSERVABLES = ["obs_rel_egg_price", "obs_rel_chicken_price", "obs_egg_coverage",
               "obs_chicken_coverage", "obs_pullet_placement_growth",
               "obs_opening_rate", "obs_suspended_share", "obs_feed_price"]


def counterfactual_params(params: dict) -> dict:
    """Same scenario with the programme switched off (start pushed beyond the horizon)."""
    p = dict(params)
    p["Programme start time"] = 10_000
    return p


CF_COLS = ["Relative egg price", "Relative chicken price",
           "Household egg consumption ratio", "Household chicken consumption ratio"]


def compute_outcomes(df: pd.DataFrame, cf: pd.DataFrame) -> dict:
    """Programme-attributable indicators: run WITH programme minus SAME scenario WITHOUT it.

    This separates the programme's effect from exogenous shocks (feed, disease) that
    would raise prices anyway.
    """
    post = df.index >= PROGRAMME_START
    ex_egg = (df["Relative egg price"] - cf["Relative egg price"])[post]
    ex_chk = (df["Relative chicken price"] - cf["Relative chicken price"])[post]
    hh_egg = (cf["Household egg consumption ratio"] - df["Household egg consumption ratio"])[post]
    hh_chk = (cf["Household chicken consumption ratio"] - df["Household chicken consumption ratio"])[post]
    active = df[(df["Programme coverage"] > 0.5)]
    last = df.loc[df.index >= df.index.max() - 52]
    out = {
        "peak_egg_price": float(ex_egg.max()),
        "peak_chicken_price": float(ex_chk.max()),
        "weeks_egg_above_thr": int((ex_egg > SPIKE_THRESHOLD).sum()),
        "weeks_chicken_above_thr": int((ex_chk > SPIKE_THRESHOLD).sum()),
        "hh_egg_loss": float(hh_egg.mean()),
        "hh_chicken_loss": float(hh_chk.mean()),
        "egg_margin_volatility": float(df.loc[post, "Egg farmer margin"].std()),
        "mean_cost_per_portion": float(active["Protein cost per portion"].mean()) if len(active) else np.nan,
        "mean_coverage_last52": float(last["Programme coverage"].mean()),
        "raw_peak_egg_price": float(df.loc[post, "Relative egg price"].max() - 1),
        "raw_peak_chicken_price": float(df.loc[post, "Relative chicken price"].max() - 1),
    }
    # early-warning observables (things a ministry can actually monitor)
    w = EARLY_WARNING_WEEK
    row = df.loc[w]
    base_place = df.loc[PROGRAMME_START, "Pullet placement"]
    out.update({
        "obs_rel_egg_price": row["Relative egg price"],
        "obs_rel_chicken_price": row["Relative chicken price"],
        "obs_egg_coverage": row["Relative egg coverage"],
        "obs_chicken_coverage": row["Relative chicken coverage"],
        "obs_pullet_placement_growth": row["Pullet placement"] / base_place - 1,
        "obs_opening_rate": row["Kitchen opening rate"],
        "obs_suspended_share": row["Suspended kitchens"] / max(1.0, row["Operational kitchens"] + row["Suspended kitchens"]),
        "obs_feed_price": row["Relative feed price"],
    })
    return out


def is_spike(df_out: pd.DataFrame) -> pd.Series:
    return (df_out["peak_egg_price"] > SPIKE_THRESHOLD) | (df_out["peak_chicken_price"] > SPIKE_THRESHOLD)


# --------------------------------------------------------------------- model access
_MODEL = None


def load_model():
    """Translate the Vensim file once per process (PySD writes mbg_poultry.py)."""
    global _MODEL
    if _MODEL is None:
        import pysd
        _MODEL = pysd.read_vensim(str(MODEL_FILE))
    return _MODEL


def run(params: dict | None = None, time_step: float | None = None,
        columns: list[str] | None = None) -> pd.DataFrame:
    m = load_model()
    kw = {"params": params or {}, "return_columns": columns or RETURN_COLS,
          "return_timestamps": np.arange(0, 313, 1.0)}
    if time_step is not None:
        kw["time_step"] = time_step
    m.reload()
    return m.run(**kw)


def defaults() -> dict:
    """Default (mid-case) value of each uncertainty as written in the .mdl."""
    m = load_model()
    out = {}
    for k in UNCERTAINTIES:
        out[k] = float(m[k])
    return out


# --------------------------------------------------------------------- plotting helpers
def stamp(fig):
    if DEMO:
        fig.text(0.5, 0.5, "DEMO\nplaceholder parameters", fontsize=34, color="red",
                 alpha=0.12, ha="center", va="center", rotation=25)
        fig.text(0.01, 0.005, DEMO_STAMP, fontsize=7, color="red")


def save_table(df: pd.DataFrame, name: str):
    path = OUT_DIR / name
    if DEMO:
        with open(path, "w") as f:
            f.write(f"# {DEMO_STAMP}\n")
        df.to_csv(path, mode="a")
    else:
        df.to_csv(path)
    return path


def n_jobs() -> int:
    return max(1, (os.cpu_count() or 2))
