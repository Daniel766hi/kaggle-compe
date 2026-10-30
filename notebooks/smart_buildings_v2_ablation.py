# %% [markdown]
# # Smart Buildings v2: quick ablation, then submit
#
# Notebook for the
# [NeurIPS 2026 Smart Buildings](https://www.kaggle.com/competitions/neurips-2026-smart-buildings)
# competition. It compares several controllers on a small, time-boxed set of training scenarios,
# writes one results table, and can submit any of them through the official inference server.
#
# **Variants**
# - The organizers' chain (`smart_buildings/baselines/pid.py`, `pid_plus.py`), each step adding one
#   idea: `pid` → `pid_worst` (worst zone instead of average) → `pid_econ` (economizer) →
#   `pid_prop` (proportional reheat) → `pid_water` (hot-water reset).
# - `water_sensor`: `pid_water` with `USE_SENSOR_BAND = True`. The chain can read each zone's band
#   from its own setpoint sensors (the band the reward uses), but ships with that switch off.
# - `water_precond` / `pid_precond`: `pid_water` / `pid` switched to the comfort band
#   `PRECOND_HOURS` before the weekday comfort period, so zones are in band when occupancy starts.
# - `water_sensor_precond`: `water_sensor` with pre-conditioning.
#
# `VARIANTS` picks which ones run. The first run (8 variants, 45 minutes) finished only Fairbanks:
# `pid` beat `pid_water` by 27% there, and pre-conditioning helped in both Fairbanks (-1.5%) and
# the part of Phoenix that ran (-25%). This run keeps the five that matter, across all climates.
#
# **Time saving**: 5 scenarios (one per weather station, different buildings) × `STEPS` steps
# (default 2,016 = 7 days, which includes a weekend), runs ordered scenario by scenario so a
# partial run still compares every variant on the same scenarios, and a `TIME_BUDGET_MIN` stop.
# No charts or time series are written. Scores from short runs rank the variants; they are not
# comparable with the 30-day baseline numbers (pid_water 0.0541) or the leaderboard.
#
# **Before running**
# 1. *Add Input* → competition data **neurips-2026-smart-buildings**.
# 2. *Settings*: Accelerator None (CPU), Internet off.
# 3. *Save Version* → *Save & Run All* so the experiment keeps running with the browser closed.
#    Results: `/kaggle/working/ablation_results.csv` and `ablation_summary.csv`.
#
# **Submitting**: set `SUBMIT_VARIANT`, set `RUN_EXPERIMENT = False` (faster), *Save Version*, and
# submit that version. The experiment cell is skipped automatically in the hidden rerun.

# %%
import os
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

candidates = [
    Path("/kaggle/input/competitions/neurips-2026-smart-buildings"),
    Path("/kaggle/input/neurips-2026-smart-buildings"),
]
if os.getenv("SMART_BUILDINGS_DATA_ROOT"):
    candidates.insert(0, Path(os.environ["SMART_BUILDINGS_DATA_ROOT"]))
DATA_ROOT = next((p for p in candidates if (p / "smart_buildings").exists()), None)
if DATA_ROOT is None:
    raise FileNotFoundError("Add the competition data as input, or set SMART_BUILDINGS_DATA_ROOT")
sys.path.insert(0, str(DATA_ROOT))
sys.path.insert(0, str(DATA_ROOT / "kaggle_evaluation"))
OUT_DIR = Path("/kaggle/working") if Path("/kaggle/working").exists() else Path(".")

IS_RERUN = os.getenv("KAGGLE_IS_COMPETITION_RERUN") is not None
RUN_EXPERIMENT = True
STEPS = 2016  # 288 = 1 day, 2016 = 7 days, 8640 = the full 30-day episode
TIME_BUDGET_MIN = 200
SCENARIOS = [
    "building_train_1/fairbanks_1",
    "building_train_2/phoenix_6",
    "building_train_4/denver_2",
    "building_train_5/atlanta_6",
    "building_train_7/singapore_6",
]
VARIANTS = ["pid_water", "water_precond", "pid", "pid_precond", "water_sensor"]
SUBMIT_VARIANT = "pid_water"
print("Competition data:", DATA_ROOT, "| hidden rerun:", IS_RERUN)

# %%
from kaggle_evaluation import smart_buildings_inference_server
from smart_buildings.baselines.pid import PIDPolicy
from smart_buildings.baselines.pid_plus import (
    PIDEconomizerPolicy,
    PIDProportionalReheatPolicy,
    PIDWaterResetPolicy,
    PIDWorstZonePolicy,
)


class WaterSensorPolicy(PIDWaterResetPolicy):
    """pid_water judging each zone against its own setpoint sensors."""

    USE_SENSOR_BAND = True


class PrecondMixin:
    """Holds the comfort band from PRECOND_HOURS before the weekday start.

    The PID policies pick their band from the hour of day in several places, so the hour is shifted
    to the comfort start inside the pre-conditioning window. While that window is active, zones are
    judged against the comfort band even when sensor bands are on, since the sensors still report
    eco. `pid` has no per-zone band, so only the hour shift applies to it.
    """

    PRECOND_HOURS = 1

    def _get_hour_and_day(self, obs):
        hour, day = super()._get_hour_and_day(obs)
        start = self.morning_start_hour
        self._precond = day < 5 and start - self.PRECOND_HOURS <= hour < start
        return (start, day) if self._precond else (hour, day)

    def _zone_band(self, obs, vav_id, low, high):
        if getattr(self, "_precond", False):
            return low, high
        return super()._zone_band(obs, vav_id, low, high)


class WaterPrecondPolicy(PrecondMixin, PIDWaterResetPolicy):
    pass


class WaterSensorPrecondPolicy(WaterPrecondPolicy):
    USE_SENSOR_BAND = True


class PIDPrecondPolicy(PrecondMixin, PIDPolicy):
    pass


POLICIES = {
    "pid": PIDPolicy,
    "pid_worst": PIDWorstZonePolicy,
    "pid_econ": PIDEconomizerPolicy,
    "pid_prop": PIDProportionalReheatPolicy,
    "pid_water": PIDWaterResetPolicy,
    "water_sensor": WaterSensorPolicy,
    "water_precond": WaterPrecondPolicy,
    "water_sensor_precond": WaterSensorPrecondPolicy,
    "pid_precond": PIDPrecondPolicy,
}


class SubmissionPolicy(smart_buildings_inference_server.Policy):
    """Adapter between the inference server and the chosen variant.

    The variant is held rather than inherited because PIDPolicy.__init__ does not call
    super().__init__. Actions are cast and clipped, since the gateway rejects out-of-range ones.
    """

    def __init__(self, building_meta_data, action_spec):
        super().__init__(building_meta_data, action_spec)
        self.policy = POLICIES[SUBMIT_VARIANT](building_meta_data, action_spec)
        self.continuous_space = action_spec["continuous_action"]
        self.discrete_space = action_spec["discrete_action"]

    def get_action(self, obs: np.ndarray) -> dict[str, np.ndarray]:
        action = self.policy.get_action(obs)
        continuous = np.asarray(action["continuous_action"], dtype=np.float32)
        discrete = np.asarray(action["discrete_action"])
        return {
            "continuous_action": np.clip(
                continuous, self.continuous_space.low, self.continuous_space.high
            ).astype(np.float32),
            "discrete_action": np.clip(
                np.rint(discrete), self.discrete_space.low, self.discrete_space.high
            ).astype(np.int32),
        }


# %% [markdown]
# ## Experiment
#
# Per run: score = |total reward / steps| (lower is better), plus the mean per-step comfort
# regret, energy cost and carbon terms from the reward, to show where each variant gains or loses.
# The scenario configs use paths relative to the data folder and the simulator writes next to
# them, so the package is copied to a writable folder and run from there.

# %%
def run_one(scenario: str, variant: str) -> dict:
    from smart_buildings.evaluate import (
        SimulationTracker,
        create_building_meta_data,
        initialize_policy,
        load_hybrid_environment,
        run_policy,
    )

    input_dir = Path("smart_buildings/training_scenarios") / scenario
    env = load_hybrid_environment(input_dir / "config.gin")
    env.metrics_path = None
    env._occupancy_normalization_constant = 125.0
    tracker = SimulationTracker(env, vmin=280, vmax=310, capture_snapshots=False)
    meta = create_building_meta_data(env, input_dir)
    policy = initialize_policy(POLICIES[variant], meta, env.action_spec())

    start = time.time()
    summary = run_policy(env, tracker, policy, STEPS)
    steps = summary["num_steps"]
    row = {
        "scenario": scenario,
        "station": scenario.split("/")[1].rsplit("_", 1)[0],
        "variant": variant,
        "steps": steps,
        "score": abs(summary["total_reward"]) / steps,
        "seconds": round(time.time() - start, 1),
    }
    components = pd.DataFrame(tracker.reward_components)
    for column in ("normalized_productivity_regret", "normalized_energy_cost", "normalized_carbon_emission"):
        if column in components:
            row[column.replace("normalized_", "")] = float(components[column].mean())
    del env, tracker
    return row


def run_experiment() -> pd.DataFrame:
    work = OUT_DIR / "sb"
    if not (work / "smart_buildings").exists():
        shutil.copytree(DATA_ROOT / "smart_buildings", work / "smart_buildings")

    rows, durations = [], []
    budget = TIME_BUDGET_MIN * 60
    began = time.time()
    cwd = os.getcwd()
    os.chdir(work)
    try:
        for scenario in SCENARIOS:
            for variant in VARIANTS:
                expected = np.mean(durations) if durations else 0.0
                if time.time() - began + expected > budget:
                    print(f"Time budget reached before {scenario} / {variant}.")
                    return pd.DataFrame(rows)
                row = run_one(scenario, variant)
                durations.append(row["seconds"])
                rows.append(row)
                print(f"{scenario:30s} {variant:22s} score {row['score']:.5f}  ({row['seconds']:.0f}s)", flush=True)
                pd.DataFrame(rows).to_csv(OUT_DIR / "ablation_results.csv", index=False)
    finally:
        os.chdir(cwd)
    return pd.DataFrame(rows)


def summarize(results: pd.DataFrame) -> pd.DataFrame:
    # Only scenarios every variant finished, so the comparison is like for like.
    counts = results.groupby("scenario")["variant"].nunique()
    complete = counts[counts == results["variant"].nunique()].index
    done = results[results["scenario"].isin(complete)]
    if done.empty:
        print("No scenario finished for every variant; raise TIME_BUDGET_MIN or lower STEPS.")
        return done
    by_station = done.pivot_table(index="variant", columns="station", values="score")
    summary = done.groupby("variant").mean(numeric_only=True).drop(columns=["steps"])
    summary = summary.join(by_station).sort_values("score")
    reference = summary.loc["pid_water", "score"] if "pid_water" in summary.index else np.nan
    summary.insert(1, "vs_pid_water_%", 100 * (summary["score"] / reference - 1))
    summary.to_csv(OUT_DIR / "ablation_summary.csv")
    print(f"\n{len(complete)} scenario(s) x {STEPS} steps. Lower is better.")
    return summary.round(5)


if RUN_EXPERIMENT and not IS_RERUN:
    results = run_experiment()
    print(summarize(results).to_string())

# %% [markdown]
# ## Inference server
#
# Keep this as the last cell. It serves `SUBMIT_VARIANT` to the evaluation gateway.

# %%
print("Serving variant:", SUBMIT_VARIANT)
smart_buildings_inference_server.SmartBuildingsInferenceServer(SubmissionPolicy).run(
    competition_data_folder=str(DATA_ROOT),
)
