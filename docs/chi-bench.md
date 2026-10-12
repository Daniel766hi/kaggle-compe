# chi-pilot: an agent for the χ-Bench Kaggle competition

chi-pilot is an agent harness for [χ-Bench](https://github.com/actava-ai/chi-bench) (IEEE Big Data
Cup 2026, Kaggle competition `chi-bench`). It runs inside the official χ-Bench tooling, so trials,
verifier scores, evidence packets and the private-final package all use the standard flow.

## Design

The strongest agent in the χ-Bench paper is Claude Code with a Claude model (28% pass@1), and
most failures are workflow mistakes rather than missing knowledge: skipped steps, wrong record
fields, overstated evidence, missing letters or artifacts. chi-pilot keeps Claude Code and adds:

| Part | What it does | Code |
|---|---|---|
| Track guides | Detects the track (provider PA, payer UM, care management) from the instruction and appends an operating guide to Claude Code's system prompt: the workflow order, the tools at each step, honesty and scope rules, and how to write policy-grounded rationale. | `chi_pilot/domains.py`, `chi_pilot/playbooks.py` |
| Handbook search | `hb-search "<terms>"`: ranked (BM25) search over the 1,279-document handbook, so the agent finds the governing policy before reading it in full. | `chi_pilot/hb_search.py` |
| Completion audit | A Claude Code Stop hook. The first time the agent tries to finish, it gets a track-specific checklist and must verify its work with read-only tools and fix gaps, in the same session. | `chi_pilot/stop_hook.py` |
| Defaults | High reasoning effort; optional Claude Code version pin. | `chi_pilot/harness.py` |

Everything runs as one Claude Code session, so Harbor's trajectory, token and cost accounting
work unchanged (cost and tool calls are tie-breakers in the final ranking).

The guides contain general workflow knowledge only: no task answers, and no handbook text. The
agent reads policy from the handbook at run time and is told never to read hidden grading files.

## Rules to keep in mind

- The handbook is gated and licensed for non-commercial research. Never commit it, upload it to
  Kaggle, or paste substantial excerpts into this repo, reports or notebooks.
- Never commit `.env`, API keys or Hugging Face tokens.
- Each public task is run once for the Kaggle score; rewards come only from the official
  verifier.
- Freeze the final system (code, prompts, model id, Claude Code version) by the final submission
  deadline, November 15, 2026.

## Setup

Requirements: Python 3.12+, Docker, [uv](https://github.com/astral-sh/uv), an approved Hugging Face
token for the handbook, and an Anthropic API key (it pays for both the agent and the judge).

```bash
# 1. χ-Bench, next to this repo
git clone https://github.com/actava-ai/chi-bench ../chi-bench
cd ../chi-bench
uv sync --extra dev

# 2. Public tasks (pinned release)
uv run huggingface-cli login
REV=chi-bench-v1.0.0
uv run huggingface-cli download actava/chi-bench --repo-type dataset --revision "$REV" --local-dir data/
echo "$REV" > data/.chi-bench-version

# 3. Handbook (only after your access request is approved)
uv run huggingface-cli download actava/managed-care-operations-handbook \
  --repo-type dataset --local-dir data/skills/

# 4. Data corrections required by χ-Bench v1.1.0, then the image
uv run playwright install chromium
uv run python scripts/repair_pa_t035.py
uv run python scripts/regenerate_payer_request_forms.py
uv run cb docker build
uv run cb data verify

# 5. Install chi-pilot into the checkout (re-run after every change to chi_pilot/)
python ../kaggle-compe/scripts/install_chi_pilot.py --chi-bench .
uv run cb agent list          # chi-pilot is listed as in-tree

# 6. Credentials (local only)
cp .env.example .env          # set ANTHROPIC_API_KEY
```

The harness copies its helper scripts into each trial container at start, so changing
`chi_pilot/` only needs step 5 again, not a new image.

Optional: `uv run modal setup` to run trials in parallel on Modal (recommended for full runs). For
local Docker runs set `run.environment: docker` in the config and lower `concurrency`.

## Smoke test

Run one task per track before a full run:

```bash
M=anthropic/claude-opus-5-5
uv run cb experiment run --agent chi-pilot --model $M \
  --dataset data/prior_auth_um/tasks/pa_t008_t008_o002_p01_mdreview_payer
uv run cb experiment run --agent chi-pilot --model $M \
  --dataset data/prior_auth_provider/tasks/$(ls data/prior_auth_provider/tasks | head -1)
uv run cb experiment run --agent chi-pilot --model $M \
  --dataset data/care_management/tasks/$(ls data/care_management/tasks | head -1)
```

Each trial writes `logs/experiments/.../trial_*/`. Check:

- `result.json` and `verifier/reward.json`: the binary reward.
- `verifier/scorecard.json`: `failed_checks` explains a failure; `fractional_reward` shows near
  misses.
- `agent/chi-pilot/domain`: the track chi-pilot detected (should match the task).
- `agent/chi-pilot/audit_rounds`: `1` means the completion audit ran.
- `agent/claude-code.txt`: the full Claude Code stream.

## Full public run and Kaggle submission

```bash
cp ../kaggle-compe/configs/chi_bench/chi-pilot.yaml configs/submissions/chi-pilot.yaml
# edit team and contact

uv run cb submission validate -f configs/submissions/chi-pilot.yaml
uv run cb submission run      -f configs/submissions/chi-pilot.yaml
uv run cb submission status   -f configs/submissions/chi-pilot.yaml
uv run cb submission prepare  -f configs/submissions/chi-pilot.yaml

# Kaggle file: one row per public task, task_id,reward
PYTHONPATH=../kaggle-compe python -m chi_pilot.kaggle_csv \
  --trials logs/submissions/chi-pilot-opus-5-5 --data-root data --out submission.csv
```

Upload `submission.csv` to the Kaggle competition (up to 5 submissions a day; select one as
final). Tasks without a verified trial are written as 0 and listed as a warning.

## Running from a Kaggle notebook

`notebooks/chi_pilot_run.py` does the setup, the run and the Kaggle file in one private Kaggle
notebook. Kaggle cannot run Docker, so trials run on Modal (you pay Modal and Anthropic).

```bash
python scripts/push_notebooks.py chi-pilot     # pushes it private, with internet on
```

On Kaggle: attach the secrets `ANTHROPIC_API_KEY`, `HF_TOKEN`, `MODAL_TOKEN_ID` and
`MODAL_TOKEN_SECRET` (Add-ons → Secrets) and the `chi-pilot-agent` dataset, set `TEAM`,
`CONTACT` and `MODE` in the settings cell, then run `MODE = "smoke"` first. For `MODE = "full"`
use *Save Version* → *Save & Run All*. The handbook and task data only go to a temporary
directory. The evidence packet goes to the private Modal volume `chi-pilot-packets`, not to the
notebook outputs, because trajectories can quote the handbook. The notebook must stay private;
the push script refuses `--public` for it.

## Private-final package (due November 15, 2026)

Email `research@actava.ai` with `[Kaggle]` in the subject and your team details, containing:

- the evidence packet from `cb submission prepare` (`logs/submissions/<id>/packet/...`);
- the agent source: this repo's `chi_pilot/`, `scripts/install_chi_pilot.py` and the config;
- prompts and configuration (all in `chi_pilot/playbooks.py` and the config), dependency
  manifests and lock files (χ-Bench's `uv.lock` plus the Claude Code version used);
- exact model and endpoint identifiers (for example `claude-opus-5-5` on the Anthropic API);
- reproduction steps (this document) or the image digest from the packet's `provenance.json`;
- cost and token records (in the packet);
- a qualifying technical report, IEEE conference template, at most 5 pages plus references.

Before the freeze, pin the Claude Code version you tested with: set
`CHI_PILOT_CLAUDE_CODE_VERSION` in `.env` and record it in the report.

## Settings

Read from `.env` on the host:

| Variable | Default | Meaning |
|---|---|---|
| `CHI_PILOT_AUDIT_ROUNDS` | `1` | Completion audits per task; `0` disables the Stop hook. |
| `CHI_PILOT_EFFORT` | `high` | Claude Code effort (`low`, `medium`, `high`, `xhigh`, `max`). |
| `CHI_PILOT_CLAUDE_CODE_VERSION` | latest | Claude Code release installed in each trial. |

In a flat experiment config (`cb experiment run -f ...`), `agent_kwargs` can also set the stock
Claude Code options: `reasoning_effort`, `max_turns`, `max_budget_usd`, `append_system_prompt`
(added after the chi-pilot guide).

## Improving the agent

1. Run a track (`cb submission run ... --domain pa|um|cm`) and collect `failed_checks` from the
   scorecards.
2. Group failures by cause (workflow step skipped, wrong field, letter missing, overstated
   evidence, outreach consent issue) and fix the cause in the general guide or the audit
   checklist in `chi_pilot/playbooks.py`. Keep changes general: the private tasks are different
   cases, and hard-coding public-task answers is prohibited.
3. Re-install (step 5) and re-run the affected tasks. Use `run.n_attempts: 3` on your own
   development runs to measure pass^3 (the reliability tie-breaker and award); the Kaggle file
   still uses the first attempt only.

## Tests

```bash
pytest -q tests/test_chi_pilot.py
```

The harness tests need Harbor and are skipped outside a χ-Bench environment; to run them, use
χ-Bench's interpreter from this repo: `../chi-bench/.venv/bin/python -m pytest tests/test_chi_pilot.py`.
