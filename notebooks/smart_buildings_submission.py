# %% [markdown]
# # Smart Buildings: submission notebook
#
# Submission notebook for the
# [NeurIPS 2026 Smart Buildings](https://www.kaggle.com/competitions/neurips-2026-smart-buildings)
# competition. It runs one HVAC control policy through the official inference server, and can
# also score that policy on the 30 training scenarios before you submit.
#
# The policy starts as the organizers' `pid_water` baseline (`PIDWaterResetPolicy`, Apache-2.0,
# shipped in the competition data). Submit it unchanged first: its training score is known
# (0.0541 over the 30 training scenarios, from the starter kit's `baseline_returns.json`), so the
# leaderboard number shows how the hidden scenarios compare. Then put your changes in `MyPolicy`.
#
# **Before running**
# 1. Join the competition and accept the rules.
# 2. *Add Input* → the competition data **neurips-2026-smart-buildings**.
# 3. *Settings* → *Accelerator*: None (CPU is enough). *Internet*: off. Submissions must run
#    without internet.
#
# **Local scoring** (cell 3) is skipped during the hidden rerun. Set `LOCAL_EVAL` to `"smoke"`
# (one scenario, one day), `"scenario"` (one scenario, 30 days) or `"full"` (30 scenarios,
# 30 days; use *Save Version* → *Save & Run All* so it keeps running with the browser closed).
# Only 30-day runs are comparable with the baseline scores.
#
# **Submitting**: *Save Version*, then submit that version from the competition's
# *Submit Prediction* page. The last cell starts the inference server; when you run the
# notebook yourself it plays one public example scenario, and on submission it plays the hidden
# test scenarios.

# %%
import json
import os
import shutil
import sys
import time
from pathlib import Path

import numpy as np

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

IS_RERUN = os.getenv("KAGGLE_IS_COMPETITION_RERUN") is not None
LOCAL_EVAL = "smoke"  # "off", "smoke", "scenario" or "full"
print("Competition data:", DATA_ROOT, "| hidden rerun:", IS_RERUN)

# %%
from kaggle_evaluation import smart_buildings_inference_server
from smart_buildings.baselines.pid_plus import PIDWaterResetPolicy


class MyPolicy(PIDWaterResetPolicy):
    """Your controller. As shipped it is exactly the organizers' pid_water baseline.

    Override `get_action(obs)` (call `super().get_action(obs)` and adjust the result) or any of
    the hooks in smart_buildings/baselines/pid_plus.py. Read action positions from
    `building_meta_data` (`temp_indices`, `pressure_indices`, `recirculation_indices`,
    `water_indices`, `zone_action_indices`) instead of assuming an order.
    """


class SubmissionPolicy(smart_buildings_inference_server.Policy):
    """Adapter between the inference server and MyPolicy.

    MyPolicy is held rather than inherited because PIDPolicy.__init__ does not call
    super().__init__, so a combined subclass would skip the server's Policy.__init__. Actions are
    cast and clipped to the action space, since the gateway rejects out-of-range actions.
    """

    def __init__(self, building_meta_data, action_spec):
        super().__init__(building_meta_data, action_spec)
        self.policy = MyPolicy(building_meta_data, action_spec)
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
# ## Local scoring on the training scenarios
#
# Score = mean over scenarios of |total reward / steps|, the leaderboard formula. Lower is
# better. Reference scores over all 30 training scenarios at 8,640 steps: `pid_water` 0.0541,
# `fixed_setpoint` 0.0659, `pid` 0.0674, `bang_bang` 0.2252.
#
# The scenario configs use paths relative to the data folder and the simulator writes files
# next to them, so the package is copied to `/kaggle/working/sb` (read-only input otherwise)
# and run from there.

# %%
def local_eval(mode: str) -> dict[str, float]:
    if mode == "off":
        return {}
    work = Path("/kaggle/working/sb") if Path("/kaggle/working").exists() else Path("sb_work")
    if not (work / "smart_buildings").exists():
        shutil.copytree(DATA_ROOT / "smart_buildings", work / "smart_buildings")

    from smart_buildings.evaluate import evaluate_policy_for_config

    scenarios = sorted((work / "smart_buildings/training_scenarios").glob("building_*/*"))
    steps = 8640
    if mode in ("smoke", "scenario"):
        scenarios = [s for s in scenarios if s.parent.name == "building_train_1" and s.name == "fairbanks_1"]
        steps = 288 if mode == "smoke" else 8640

    results_dir = work / "results"
    per_step = {}
    cwd = os.getcwd()
    os.chdir(work)
    try:
        for scenario in scenarios:
            name = f"{scenario.parent.name}/{scenario.name}"
            start = time.time()
            summary = evaluate_policy_for_config(
                scenario_results_dir=results_dir / scenario.parent.name / scenario.name,
                input_dir=scenario.relative_to(work),
                policy_key="mine",
                policy_class=MyPolicy,
                num_steps=steps,
            )
            per_step[name] = summary["total_reward"] / steps
            print(f"{name:32s} reward/step {per_step[name]:9.5f}  ({time.time() - start:.0f}s)", flush=True)
    finally:
        os.chdir(cwd)

    score = float(np.mean([abs(v) for v in per_step.values()]))
    print(f"\n{mode}: {len(per_step)} scenario(s) x {steps} steps, score {score:.5f}")
    if steps != 8640:
        print("Short episode: not comparable with the baseline scores.")
    with open(results_dir / f"scores_{mode}.json", "w") as f:
        json.dump({"steps": steps, "score": score, "reward_per_step": per_step}, f, indent=2)
    return per_step


if not IS_RERUN:
    local_eval(LOCAL_EVAL)

# %% [markdown]
# ## Inference server
#
# Keep this as the last cell. It serves `SubmissionPolicy` to the evaluation gateway.

# %%
smart_buildings_inference_server.SmartBuildingsInferenceServer(SubmissionPolicy).run(
    competition_data_folder=str(DATA_ROOT),
)
