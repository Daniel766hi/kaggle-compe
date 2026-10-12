# %% [markdown]
# # chi-pilot: run the χ-Bench agent from Kaggle
#
# This notebook runs the **chi-pilot** agent (or the stock Claude Code baseline, for
# comparison) on the χ-Bench public tasks and writes the Kaggle submission file and the result
# tables for the technical report. Kaggle notebooks cannot run Docker, so the trials run in
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
# 5. Choose `MODE` below. Start with `"dev"` (a few tasks per track). For `"full"` use
#    *Save Version* → *Save & Run All*, so the run keeps going with the browser closed.
#
# Without the secrets the notebook only prints what is missing and runs nothing.
#
# **Outputs** (in `/kaggle/working`): `submission.csv` (full mode),
# `trial_summary.csv` and `failed_checks.csv` (check names only, no handbook text). The evidence
# packet and raw trial logs contain agent trajectories, which can quote the handbook, so they go
# to the private Modal volume `chi-pilot-packets` instead (download with `modal volume get`).

# %%
MODE = "dev"                         # "dev": DEV_TASKS_PER_TRACK tasks per track; "full": all 75
AGENT = "chi-pilot"                  # "chi-pilot", or "claude-code" for the stock baseline
MODEL = "anthropic/claude-opus-5-5"  # passed to Claude Code (the "anthropic/" prefix is dropped)
AUDIT_ROUNDS = 1                     # chi-pilot completion audits per task (0 = ablation)
EFFORT = "high"                      # chi-pilot's Claude Code effort: low, medium, high, xhigh, max
N_ATTEMPTS = 1                       # 3 measures pass^3; the Kaggle file always uses attempt 1
DEV_TASKS_PER_TRACK = 1
TEAM = "CHANGE-ME"                   # Kaggle team name (used in the evidence packet)
CONTACT = "CHANGE-ME@example.com"
CONCURRENCY = 10                     # parallel Modal sandboxes per track
CLAUDE_CODE_VERSION = ""             # pin a Claude Code release before the final freeze
UPLOAD_TO_MODAL_VOLUME = True        # keep packets and trial logs in a private Modal volume

CHI_BENCH_REPO = "https://github.com/actava-ai/chi-bench"
CHI_BENCH_REF = "d46559622b1c25facaa1723db07c6562497c8086"  # χ-Bench runtime 1.1.0
DATASET_REV = "chi-bench-v1.0.0"

# %%
import glob
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

assert MODE in ("dev", "full") and AGENT in ("chi-pilot", "claude-code"), (MODE, AGENT)
LABEL = AGENT + (f"-audit{AUDIT_ROUNDS}" if AGENT == "chi-pilot" else "")
RUN_ID = f"{LABEL}-{MODEL.split('/')[-1]}".replace(".", "-")
OUT = Path("/kaggle/working")
# Not /kaggle/working: nothing downloaded here may end up in the saved notebook outputs.
WORK = (Path("/kaggle/temp") if Path("/kaggle/temp").is_dir() else Path("/tmp")) / "chi-pilot-run"
CB = WORK / "chi-bench"
AGENT_SRC = WORK / "chi-pilot"
UV = [sys.executable, "-m", "uv"]
TRACK_DATA = {
    "pa_provider": "data/prior_auth_provider",
    "pa_um": "data/prior_auth_um",
    "cm": "data/care_management",
}


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
secrets, missing = {}, []
try:
    from kaggle_secrets import UserSecretsClient
except ImportError:  # outside Kaggle: read the same names from the environment
    UserSecretsClient = None
for name in ("ANTHROPIC_API_KEY", "HF_TOKEN", "MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET"):
    try:
        value = UserSecretsClient().get_secret(name) if UserSecretsClient else os.environ[name]
        secrets[name] = value
    except Exception:
        missing.append(name)
READY = not missing
if READY:
    print("secrets attached:", ", ".join(secrets))
else:
    print("NOT RUNNING. Attach these Kaggle secrets (Add-ons → Secrets), then run again:")
    for name in missing:
        print("  -", name)

# %% [markdown]
# ## 2. Steps
#
# Each step is a function; the last cell runs them in order.

# %%
def setup_chi_bench():
    """χ-Bench at the pinned commit, the public tasks, the handbook and the data corrections."""
    WORK.mkdir(parents=True, exist_ok=True)
    run([sys.executable, "-m", "pip", "install", "-q", "uv"], cwd=WORK)
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

    # Required by χ-Bench 1.1.0; the scripts render PDFs with Chromium.
    run(UV + ["run", "playwright", "install", "--with-deps", "chromium"])
    run(UV + ["run", "python", "scripts/repair_pa_t035.py"])
    run(UV + ["run", "python", "scripts/regenerate_payer_request_forms.py"])
    run(UV + ["run", "cb", "data", "verify"])


def install_agent():
    """Install chi-pilot from the input dataset, write .env and the Modal profile."""
    found = glob.glob("/kaggle/input/**/chi_pilot/harness.py", recursive=True)
    if not found:
        raise RuntimeError("Add the chi-pilot-agent dataset as an input to this notebook.")
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
              "--token-id", secrets["MODAL_TOKEN_ID"],
              "--token-secret", secrets["MODAL_TOKEN_SECRET"]], echo=False)


def submission_config():
    path = CB / "configs" / "submissions" / f"{RUN_ID}.yaml"
    path.write_text(f"""\
schema: chi-bench/submission/v1
submission:
  id: {RUN_ID}
  team: {json.dumps(TEAM)}
  contact: {json.dumps(CONTACT)}
  agent: {AGENT}
  model: {MODEL}
  notes: Run from a Kaggle notebook on Modal ({LABEL}).
run:
  environment: modal
  n_attempts: {N_ATTEMPTS}
  concurrency: {CONCURRENCY}
  max_retries: 2
  timeout_multiplier: 2.0
  env_file: .env
dataset:
  version: {DATASET_REV}
  domains: [pa_provider, pa_um, cm]
""")
    run(UV + ["run", "cb", "submission", "validate", "-f", path])
    return path


def run_dev():
    """The first DEV_TASKS_PER_TRACK tasks of each track, N_ATTEMPTS times each."""
    trials = WORK / "trials" / RUN_ID
    for track, rel in TRACK_DATA.items():
        tasks = sorted(p.name for p in (CB / rel / "tasks").iterdir() if p.is_dir())
        selected = tasks[:DEV_TASKS_PER_TRACK]
        print(f"\n=== {track}: {', '.join(selected)}")
        config = WORK / f"dev-{track}.yaml"
        config.write_text(json.dumps({  # JSON is valid YAML
            "dataset": str(CB / rel / "tasks"),
            "registry_path": str(CB / rel / "registry.json"),
            "agent": AGENT,
            "model": MODEL,
            "concurrency": CONCURRENCY,
            "n_attempts": N_ATTEMPTS,
            "max_retries": 2,
            "environment": "modal",
            "env_file": ".env",
            "timeout_multiplier": 2.0,
            "include_task_name": selected,
            "trials_dir": str(trials / track),
            "job_name": f"{RUN_ID}__{track}",
        }))
        run(UV + ["run", "cb", "experiment", "run", "-f", config], check=False)
    return trials


def run_full(config):
    """Every public task, as for the Kaggle submission, then the evidence packet."""
    run(UV + ["run", "cb", "submission", "run", "-f", config], check=False)
    run(UV + ["run", "cb", "submission", "status", "-f", config])
    run(UV + ["run", "cb", "submission", "prepare", "-f", config])
    return CB / "logs" / "submissions" / RUN_ID


def write_results(trials):
    """trial_summary.csv, failed_checks.csv and, for a full run, submission.csv."""
    env = {"PYTHONPATH": str(AGENT_SRC)}
    run([sys.executable, "-m", "chi_pilot.results", "--trials", trials, "--label", LABEL,
         "--out", OUT], env=env)
    if MODE == "full":
        run([sys.executable, "-m", "chi_pilot.kaggle_csv", "--trials", trials,
             "--data-root", CB / "data", "--out", OUT / "submission.csv"], env=env)
        print("submit /kaggle/working/submission.csv from the Output tab, or with")
        print('  kaggle competitions submit chi-bench -f submission.csv -m ' + repr(LABEL))


def save_evidence(trials):
    """Copy the trial logs (and packet) to the private Modal volume, then delete local data."""
    if UPLOAD_TO_MODAL_VOLUME:
        remote = f"/{RUN_ID}-{MODE}-{time.strftime('%Y%m%d-%H%M%S')}"
        run(UV + ["run", "modal", "volume", "create", "chi-pilot-packets"], check=False)
        run(UV + ["run", "modal", "volume", "put", "chi-pilot-packets", trials, remote])
        print(f"saved to Modal volume chi-pilot-packets:{remote}")
        print(f"download: modal volume get chi-pilot-packets {remote} ./chi-pilot-evidence")
    shutil.rmtree(WORK, ignore_errors=True)
    print("temporary files (tasks, handbook, logs) removed from this session")


# %% [markdown]
# ## 3. Run

# %%
if READY:
    started = time.time()
    setup_chi_bench()
    install_agent()
    config = submission_config()
    trials = run_dev() if MODE == "dev" else run_full(config)
    print(f"\ntrials finished in {(time.time() - started) / 60:.0f} min")
    write_results(trials)
    save_evidence(trials)
else:
    print("Skipped: secrets missing (see section 1).")
