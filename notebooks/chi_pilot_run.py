# %% [markdown]
# # chi-pilot: run the χ-Bench agent from Kaggle
#
# This notebook runs the **chi-pilot** agent on the χ-Bench public tasks and writes the Kaggle
# submission file. Kaggle notebooks cannot run Docker, so the trials run in
# [Modal](https://modal.com) sandboxes (χ-Bench's recommended backend); this notebook only
# orchestrates them.
#
# **Before running**
# 1. Keep this notebook **private**. It downloads the gated Managed-Care Operations Handbook,
#    which must never be published or saved to Kaggle. Everything downloaded goes to a temporary
#    directory, never to `/kaggle/working`.
# 2. *Settings* → *Internet* on.
# 3. *Add-ons* → *Secrets*, attach:
#    - `ANTHROPIC_API_KEY`: pays for the agent and for the official judge;
#    - `HF_TOKEN`: a Hugging Face token approved for `actava/managed-care-operations-handbook`;
#    - `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET`: from `modal token new` or modal.com → Settings.
# 4. Add the dataset **chi-pilot-agent** (the agent's source) as input.
# 5. Set `MODE` below. Start with `"smoke"` (one task per track). For `"full"` use
#    *Save Version* → *Save & Run All*, so the run keeps going with the browser closed.
#
# **Outputs** (in `/kaggle/working`): `submission.csv` (full mode), `trial_summary.csv` and
# `failed_checks.csv` (check names only). The evidence packet needed for the private-final
# package contains agent trajectories, which can quote the handbook, so it is not saved here:
# it goes to the Modal volume `chi-pilot-packets` (download it with `modal volume get`).

# %%
MODE = "smoke"                       # "smoke": first task of each track; "full": all 75 tasks
MODEL = "anthropic/claude-opus-5-5"  # passed to Claude Code (the "anthropic/" prefix is dropped)
TEAM = "CHANGE-ME"                   # Kaggle team name (used in the evidence packet)
CONTACT = "CHANGE-ME@example.com"
CONCURRENCY = 10                     # parallel Modal sandboxes per track
AUDIT_ROUNDS = 1                     # chi-pilot completion audits per task (0 disables)
EFFORT = "high"                      # Claude Code effort: low, medium, high, xhigh, max
CLAUDE_CODE_VERSION = ""             # pin a Claude Code release before the final freeze
UPLOAD_TO_MODAL_VOLUME = True        # keep packets and trial logs in a private Modal volume

CHI_BENCH_REPO = "https://github.com/actava-ai/chi-bench"
CHI_BENCH_REF = "d46559622b1c25facaa1723db07c6562497c8086"  # χ-Bench runtime 1.1.0
DATASET_REV = "chi-bench-v1.0.0"
SUBMISSION_ID = "chi-pilot-" + MODEL.split("/")[-1].replace(".", "-")

# %%
import csv
import glob
import json
import os
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

OUT = Path("/kaggle/working")
# Not /kaggle/working: nothing downloaded here may end up in the saved notebook outputs.
WORK = (Path("/kaggle/temp") if Path("/kaggle/temp").is_dir() else Path("/tmp")) / "chi-pilot-run"
CB = WORK / "chi-bench"
WORK.mkdir(parents=True, exist_ok=True)
assert MODE in ("smoke", "full"), MODE


def run(cmd, cwd=CB, env=None, echo=True, check=True):
    """Run a command, streaming its output. `echo=False` hides the command line (secrets)."""
    if echo:
        print("$", " ".join(map(str, cmd)), flush=True)
    proc = subprocess.Popen(
        list(map(str, cmd)), cwd=cwd, env={**os.environ, **(env or {})},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    for line in proc.stdout:
        print(line, end="", flush=True)
    if proc.wait() != 0 and check:
        raise RuntimeError(f"command failed with exit code {proc.returncode}")
    return proc.returncode


# %% [markdown]
# ## 1. Secrets

# %%
from kaggle_secrets import UserSecretsClient

secrets, missing = {}, []
for name in ("ANTHROPIC_API_KEY", "HF_TOKEN", "MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET"):
    try:
        secrets[name] = UserSecretsClient().get_secret(name)
    except Exception:
        missing.append(name)
if missing:
    raise SystemExit(f"Attach these Kaggle secrets (Add-ons → Secrets), then rerun: {', '.join(missing)}")
print("secrets attached:", ", ".join(secrets))

# %% [markdown]
# ## 2. χ-Bench, tasks and handbook

# %%
run([sys.executable, "-m", "pip", "install", "-q", "uv"], cwd=WORK)
UV = [sys.executable, "-m", "uv"]

if not (CB / ".git").is_dir():
    run(["git", "clone", "-q", CHI_BENCH_REPO, CB], cwd=WORK)
run(["git", "checkout", "-q", CHI_BENCH_REF])
run(UV + ["sync", "-q", "--extra", "dev"])

hf_env = {"HF_TOKEN": secrets["HF_TOKEN"]}
run(UV + ["run", "huggingface-cli", "download", "actava/chi-bench", "--repo-type", "dataset",
          "--revision", DATASET_REV, "--local-dir", "data/"], env=hf_env)
(CB / "data" / ".chi-bench-version").write_text(DATASET_REV + "\n")
run(UV + ["run", "huggingface-cli", "download", "actava/managed-care-operations-handbook",
          "--repo-type", "dataset", "--local-dir", "data/skills/"], env=hf_env)

# Data corrections required by χ-Bench 1.1.0 (they render PDFs with Chromium).
run(UV + ["run", "playwright", "install", "--with-deps", "chromium"])
run(UV + ["run", "python", "scripts/repair_pa_t035.py"])
run(UV + ["run", "python", "scripts/regenerate_payer_request_forms.py"])
run(UV + ["run", "cb", "data", "verify"])

# %% [markdown]
# ## 3. Install chi-pilot and configure the run

# %%
found = glob.glob("/kaggle/input/**/chi_pilot/harness.py", recursive=True)
if not found:
    raise SystemExit("Add the chi-pilot-agent dataset as an input to this notebook.")
AGENT_SRC = WORK / "chi-pilot"
shutil.rmtree(AGENT_SRC, ignore_errors=True)
shutil.copytree(Path(found[0]).parent.parent, AGENT_SRC)
run([sys.executable, AGENT_SRC / "scripts" / "install_chi_pilot.py", "--chi-bench", CB])
run(UV + ["run", "cb", "agent", "list"])

env_lines = [
    f"ANTHROPIC_API_KEY={secrets['ANTHROPIC_API_KEY']}",
    f"CHI_PILOT_AUDIT_ROUNDS={AUDIT_ROUNDS}",
    f"CHI_PILOT_EFFORT={EFFORT}",
]
if CLAUDE_CODE_VERSION:
    env_lines.append(f"CHI_PILOT_CLAUDE_CODE_VERSION={CLAUDE_CODE_VERSION}")
env_file = CB / ".env"
env_file.write_text("\n".join(env_lines) + "\n")
env_file.chmod(0o600)

# χ-Bench's Modal runner looks for the profile named "actava" by default.
run(UV + ["run", "modal", "token", "set", "--profile", "actava", "--activate",
          "--token-id", secrets["MODAL_TOKEN_ID"], "--token-secret", secrets["MODAL_TOKEN_SECRET"]],
    echo=False)

config = CB / "configs" / "submissions" / f"{SUBMISSION_ID}.yaml"
config.write_text(f"""\
schema: chi-bench/submission/v1
submission:
  id: {SUBMISSION_ID}
  team: {json.dumps(TEAM)}
  contact: {json.dumps(CONTACT)}
  agent: chi-pilot
  model: {MODEL}
  notes: Run from a Kaggle notebook on Modal.
run:
  environment: modal
  n_attempts: 1
  concurrency: {CONCURRENCY}
  max_retries: 2
  timeout_multiplier: 2.0
  env_file: .env
dataset:
  version: {DATASET_REV}
  domains: [pa_provider, pa_um, cm]
""")
run(UV + ["run", "cb", "submission", "validate", "-f", config])

# %% [markdown]
# ## 4. Run
#
# Smoke mode runs the first task of each track. Full mode runs every public task once
# (pass@1), as the Kaggle rules require, and then prepares the evidence packet.

# %%
TRACK_DIRS = {
    "pa_provider": "data/prior_auth_provider/tasks",
    "pa_um": "data/prior_auth_um/tasks",
    "cm": "data/care_management/tasks",
}
started = time.time()
if MODE == "smoke":
    TRIALS = WORK / "smoke"
    for track, rel in TRACK_DIRS.items():
        task = sorted(p for p in (CB / rel).iterdir() if p.is_dir())[0]
        print(f"\n=== {track}: {task.name}")
        run(UV + ["run", "cb", "experiment", "run", "--dataset", task, "--agent", "chi-pilot",
                  "--model", MODEL, "-e", "modal", "--trials-dir", TRIALS / track], check=False)
else:
    TRIALS = CB / "logs" / "submissions" / SUBMISSION_ID
    run(UV + ["run", "cb", "submission", "run", "-f", config], check=False)
    run(UV + ["run", "cb", "submission", "status", "-f", config])
    run(UV + ["run", "cb", "submission", "prepare", "-f", config])
print(f"\nrun finished in {(time.time() - started) / 60:.0f} min")

# %% [markdown]
# ## 5. Results

# %%
rows, failed = [], Counter()
for result_path in TRIALS.rglob("result.json"):
    if "packet" in result_path.relative_to(TRIALS).parts:
        continue  # copies made by `cb submission prepare`
    result = json.loads(result_path.read_text())
    if not isinstance(result.get("verifier_result"), dict):
        continue
    trial = result_path.parent
    reward = json.loads((trial / "verifier" / "reward.json").read_text()).get("reward", 0) \
        if (trial / "verifier" / "reward.json").exists() else 0
    scorecard_path = trial / "verifier" / "scorecard.json"
    scorecard = json.loads(scorecard_path.read_text()) if scorecard_path.exists() else {}
    checks = scorecard.get("failed_checks") or []
    failed.update(c if isinstance(c, str) else str(c.get("name", c)) for c in checks)
    track = result_path.relative_to(TRIALS).parts[0]
    domain_file = trial / "agent" / "chi-pilot" / "domain"
    rows.append({
        "track": track,
        "task_id": result.get("task_name"),
        "reward": int(float(reward) >= 1.0),
        "fractional_reward": scorecard.get("fractional_reward"),
        "n_failed_checks": len(checks),
        "detected_track": domain_file.read_text().strip() if domain_file.exists() else "",
        "cost_usd": (result.get("agent_result") or {}).get("cost_usd"),
    })

rows.sort(key=lambda r: (r["track"], r["task_id"] or ""))
with open(OUT / "trial_summary.csv", "w", newline="") as fh:
    writer = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else ["track"])
    writer.writeheader()
    writer.writerows(rows)
with open(OUT / "failed_checks.csv", "w", newline="") as fh:
    writer = csv.writer(fh)
    writer.writerow(["check", "n_trials"])
    writer.writerows(failed.most_common())

for track in TRACK_DIRS:
    sub = [r for r in rows if r["track"] == track]
    if sub:
        print(f"{track:12s} {sum(r['reward'] for r in sub)}/{len(sub)} passed")
costs = [r["cost_usd"] for r in rows if r["cost_usd"] is not None]
if costs:
    print(f"agent cost: ${sum(costs):.2f} total, ${sum(costs) / len(costs):.2f} per task")
print("\nmost frequent failed checks:")
for check, n in failed.most_common(15):
    print(f"  {n:3d}  {check}")

# %% [markdown]
# ## 6. Kaggle submission file (full mode)
#
# One row per public task; a task without a verified trial counts as 0. Submit
# `/kaggle/working/submission.csv` from the notebook's *Output* tab or with
# `kaggle competitions submit chi-bench -f submission.csv -m "<message>"`.

# %%
if MODE == "full":
    run([sys.executable, "-m", "chi_pilot.kaggle_csv", "--trials", TRIALS,
         "--data-root", CB / "data", "--out", OUT / "submission.csv"],
        env={"PYTHONPATH": str(AGENT_SRC)})
else:
    print("smoke mode: no submission file (it needs all 75 tasks)")

# %% [markdown]
# ## 7. Keep the evidence in a private Modal volume
#
# The packet (full mode) and the raw trial logs stay out of the notebook outputs. Download
# them on your own machine with:
#
# ```bash
# modal volume ls chi-pilot-packets
# modal volume get chi-pilot-packets /<run-folder> ./chi-pilot-evidence
# ```

# %%
if UPLOAD_TO_MODAL_VOLUME:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    remote = f"/{SUBMISSION_ID}-{MODE}-{stamp}"
    run(UV + ["run", "modal", "volume", "create", "chi-pilot-packets"], check=False)
    run(UV + ["run", "modal", "volume", "put", "chi-pilot-packets", TRIALS, f"{remote}/trials"])
    print(f"saved to Modal volume chi-pilot-packets:{remote}")

# Remove the downloaded handbook and tasks from this session.
shutil.rmtree(WORK, ignore_errors=True)
print("temporary files removed")
