# Hermes Agent for this repo

[Hermes Agent](https://github.com/NousResearch/hermes-agent) (by Nous Research) is an open-source
AI agent that runs on your laptop. It reads and writes files, runs commands, and can work on a
schedule. This folder sets it up to work on this repo the way Claude Code does: read first, make
small changes, test, report honestly, and ask before anything risky.

## What's in this folder

| File | What it does | Where it goes |
|---|---|---|
| `SOUL.md` | The agent's working style and safety rules | `~/.hermes/SOUL.md` |
| `../AGENTS.md` | Project guide: layout, commands, repo rules | Stays in the repo root; Hermes reads it when you start in this folder |
| `skills/careful-engineer` | Default workflow: understand, change, test, report | `~/.hermes/skills/kaggle-compe/` |
| `skills/github-workflow` | Branches, commits, pushes, PRs, fixing failed Actions runs | 〃 |
| `skills/kaggle-datasets` | Dry-run, debug, add and publish this repo's datasets, notebooks, models | 〃 |
| `skills/kaggle-competition` | Competition loop: rules, EDA, validation, baseline, experiments, submission | 〃 |
| `skills/code-review` | Bug-focused review of a diff or PR | 〃 |
| `skills/daily-repo-check` | Read-only morning check of Actions runs and Kaggle datasets | 〃 |
| `skills/cv-tailoring` | CV review and tailoring to a job description, no invented claims | 〃 |
| `config-snippet.yaml` | Model and safety settings to paste into the Hermes config | `hermes config edit` |
| `install.ps1` / `install.sh` | Does all of the above in one go | Run once |

On native Windows, `~/.hermes` is `%LOCALAPPDATA%\hermes`.

## Before you start (5 minutes)

1. **An AI model.** How well the agent "works like Claude" depends mostly on the model behind it.
   - Closest to Claude Code: an **Anthropic API key** from
     [console.anthropic.com](https://console.anthropic.com) (pay per use; a Claude Pro
     subscription does not work in Hermes).
   - Free: a **Gemini key** from [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
     (the same key the office uses). The free tier can run out after a few agent turns.
2. **A GitHub account.** The script logs you in through the browser.
3. **A Kaggle token.** kaggle.com → *Settings* → *API* → *Generate New Token*. The script asks for
   it and saves it to `~/.kaggle/access_token`.

## Install

Clone the repo if you haven't, then from the repo folder:

**Windows (PowerShell):**

```powershell
powershell -ExecutionPolicy Bypass -File .\hermes\install.ps1
```

**macOS / Linux / WSL2:**

```bash
bash hermes/install.sh
```

The script installs Hermes, the GitHub CLI (`gh`) and the Kaggle CLI if they're missing, logs
you in to GitHub and Kaggle, installs the persona and skills, turns on "ask before risky
commands", lets you pick the model, and offers to add a daily health check. Run it again any time
to update the skills after you pull new changes.

Last step, by hand: run `hermes config edit` and paste the `approvals:` block from
`config-snippet.yaml`, so force pushes are always blocked.

## Use it

Always start Hermes **from the repo folder**, so it loads `AGENTS.md`:

```bash
cd kaggle-compe
hermes
```

Then talk to it normally, or load a skill with `/` (you can stack up to 5):

```text
/careful-engineer run the tests and tell me what's failing
/kaggle-datasets the idn-weather update failed this morning, find out why and fix it
/kaggle-datasets /careful-engineer add a dataset for Indonesian rice prices
/kaggle-competition start on <competition-slug> and build a baseline
/github-workflow commit this on a new branch, push it and open a pull request
/code-review review my changes before I push
/cv-tailoring here is a job description for a supply chain graduate program: ...
```

Hermes also ships with useful skills of its own: `github`, `systematic-debugging`,
`test-driven-development`, `requesting-code-review`, `simplify-code`, `codebase-inspection`.
See them all with `/skills`.

Useful commands inside Hermes: `/plan <task>` (write a plan before doing anything), `/model`
(switch model), `/skills`, `/cron list`.

## Automation: what runs where

| What | Runs on | When | Needs your laptop on? |
|---|---|---|---|
| Dataset updates, social posts | GitHub Actions (already set up in this repo) | Daily, 08:23 WIB and others | No |
| Morning health check (`daily-repo-check`) | Hermes cron on your laptop | 09:00 WIB | Yes, with the Hermes gateway running |

The health check only reads: it lists failed runs, paused workflows and stale Kaggle datasets,
and suggests fixes. Results are saved under `~/.hermes/cron/output/`. To get them on your phone
instead, connect a messaging app with `hermes gateway setup` (e.g. Telegram) and add
`--deliver telegram` to the job (`hermes cron edit`).

Manage jobs with `hermes cron list`, `hermes cron run <name>` (run now) and
`hermes cron pause <name>`.

## Ground rules it follows

From `SOUL.md` and `AGENTS.md`:
- It asks before pushing with force, publishing to Kaggle, submitting to a competition, posting
  to social media, spending paid credits or changing GitHub secrets.
- It tests with `--dry-run` and the offline test suite, never with real uploads.
- It never prints or commits keys (`.env`, `~/.kaggle/access_token`).
- It doesn't skip tests to make CI pass, and reports failures as they are.

You can still approve or refuse each risky command when Hermes asks (approval mode `manual`).

## If something goes wrong

- `hermes doctor` checks the installation.
- `gh auth status` and `.venv/bin/kaggle datasets list -m`
  (Windows: `.venv\Scripts\kaggle.exe datasets list -m`) check the logins.
- `hermes skills list` should show the seven skills above. If not, run the install script again.
- Edited `SOUL.md` or `AGENTS.md`? Start a new session; Hermes reads them at session start.
- Hermes docs: [hermes-agent.nousresearch.com/docs](https://hermes-agent.nousresearch.com/docs).
