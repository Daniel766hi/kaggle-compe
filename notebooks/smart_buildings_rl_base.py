# %% [markdown]
# # Smart Buildings: residual-RL base
#
# Submission-only copy of the strongest public controller for the
# [NeurIPS 2026 Smart Buildings](https://www.kaggle.com/competitions/neurips-2026-smart-buildings)
# competition, used as the base for further work:
# alex chilton's [Residual PPO](https://www.kaggle.com/code/alexchilton/yes-rl-can-run-a-building-residual-ppo)
# (public leaderboard 0.01132 on 2026-10-31), a residual network on top of malyshevdanil's per-zone
# PI rule ([Probe ZT Best](https://www.kaggle.com/code/malyshevdanil/smart-buildings-probe-zt-best)).
# Code and weights come unchanged from the dataset
# [smart-buildings-residual-rl](https://www.kaggle.com/datasets/alexchilton/smart-buildings-residual-rl)
# (Apache-2.0). Only the training demo and plots of the original notebook are left out.
#
# **Inputs**: the competition data and the dataset `alexchilton/smart-buildings-residual-rl`.
# CPU, internet off.

# %%
import os
import shutil
import sys
from pathlib import Path

candidates = [
    Path("/kaggle/input/competitions/neurips-2026-smart-buildings"),
    Path("/kaggle/input/neurips-2026-smart-buildings"),
]
DATA_ROOT = next(p for p in candidates if (p / "smart_buildings").exists())
sys.path.insert(0, str(DATA_ROOT))
sys.path.insert(0, str(DATA_ROOT / "kaggle_evaluation"))

# The dataset stores the `skynet` package flat; rebuild it as a package.
W = next(Path(p) for p, d, f in os.walk("/kaggle/input") if "skynet.pt" in f)
os.makedirs("/tmp/pkg/skynet", exist_ok=True)
for f in ("__init__.py", "base.py", "features.py", "nets.py", "policy.py", "zt_controller.py"):
    shutil.copy(W / f, f"/tmp/pkg/skynet/{f}")
sys.path.insert(0, "/tmp/pkg")
print("data", DATA_ROOT, "| weights", (W / "TAG.txt").read_text().strip())

# %%
import torch
from skynet.policy import SkynetPolicy, load
from smart_buildings.baselines.pid_plus import PIDWaterResetPolicy
from smart_buildings.evaluate import validate_action
from kaggle_evaluation import smart_buildings_inference_server as sbis

NET, PARAMS, SCALE, LATCH = load(W / "skynet.pt")
torch.set_num_threads(1)


class SubmissionPolicy(sbis.Policy):
    def __init__(self, building_meta_data, action_spec):
        super().__init__(building_meta_data, action_spec)
        self.p = SkynetPolicy(
            building_meta_data, action_spec, NET, PARAMS, SCALE, PIDWaterResetPolicy, validate_action, LATCH
        )

    def get_action(self, obs):
        return self.p.get_action(obs)


sbis.SmartBuildingsInferenceServer(SubmissionPolicy).run(competition_data_folder=str(DATA_ROOT))
