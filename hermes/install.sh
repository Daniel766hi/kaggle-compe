#!/usr/bin/env bash
# Hermes Agent setup for this repo (macOS, Linux, WSL2). Run from anywhere:
#
#   bash hermes/install.sh
#
# Installs only what's missing: Hermes Agent, the GitHub CLI and the Python packages (Kaggle CLI).
# Logs you in to GitHub and Kaggle, installs the persona (SOUL.md) and this repo's skills, and can
# add a daily 09:00 WIB health check. Safe to run again: it updates the skills and skips the rest.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
cd "$REPO"

step() { printf '\n\033[36m== %s\033[0m\n' "$1"; }
have() { command -v "$1" >/dev/null 2>&1; }
ask() { local a; read -r -p "$1 [y/N] " a; [[ "$a" =~ ^[Yy] ]]; }

step "Hermes Agent"
if ! have hermes; then
  curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
  export PATH="$HOME/.local/bin:$HERMES_HOME/bin:$PATH"
  have hermes || { echo "Hermes is installed. Open a new terminal and run this script again."; exit 0; }
fi
hermes --version || true

step "GitHub CLI"
if ! have gh; then
  if [ "$(uname)" = Darwin ]; then
    have brew || { echo "Install Homebrew from brew.sh, then run this again."; exit 1; }
    brew install gh
  elif have apt-get; then
    sudo apt-get update && sudo apt-get install -y gh
  else
    echo "Install gh from https://cli.github.com, then run this again."; exit 1
  fi
fi
gh auth status >/dev/null 2>&1 || gh auth login --web --git-protocol https
gh auth setup-git
gh auth status

step "Python packages (includes the Kaggle CLI)"
have python3 || { echo "Install Python 3.10 or newer, then run this again."; exit 1; }
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements.txt
KAGGLE="$REPO/.venv/bin/kaggle"

step "Kaggle login"
if ! "$KAGGLE" datasets list -m >/dev/null 2>&1; then
  echo "kaggle.com -> Settings -> API -> Generate New Token, then copy the token."
  (open https://www.kaggle.com/settings 2>/dev/null || xdg-open https://www.kaggle.com/settings 2>/dev/null || true)
  read -r -s -p "Paste your Kaggle API token (hidden): " token; echo
  mkdir -p "$HOME/.kaggle" && chmod 700 "$HOME/.kaggle"
  printf '%s' "$token" > "$HOME/.kaggle/access_token" && chmod 600 "$HOME/.kaggle/access_token"
  unset token
fi
if "$KAGGLE" datasets list -m >/dev/null 2>&1; then echo "Kaggle works."
else echo "Kaggle didn't accept the token. Generate a new one and run this again."; fi

step "Persona (SOUL.md) and skills"
mkdir -p "$HERMES_HOME/skills"
if [ -f "$HERMES_HOME/SOUL.md" ] && ! cmp -s hermes/SOUL.md "$HERMES_HOME/SOUL.md"; then
  cp "$HERMES_HOME/SOUL.md" "$HERMES_HOME/SOUL.md.bak"
  echo "Your previous SOUL.md is saved as SOUL.md.bak"
fi
cp hermes/SOUL.md "$HERMES_HOME/SOUL.md"
rm -rf "$HERMES_HOME/skills/kaggle-compe"
cp -R hermes/skills "$HERMES_HOME/skills/kaggle-compe"
echo "Installed skills: $(ls hermes/skills | tr '\n' ' ')"

step "Safety settings"
hermes config set approvals.mode manual
hermes config set approvals.cron_mode deny
echo "For the force-push deny list, paste the approvals block from hermes/config-snippet.yaml into 'hermes config edit'."

step "AI model (the agent's brain)"
echo "Closest to Claude Code: Anthropic with an API key (console.anthropic.com). Free option: Gemini."
if ask "Choose the model now?"; then hermes model; fi

step "Daily health check (optional)"
if ask "Add a 09:00 WIB check of GitHub Actions and Kaggle datasets?"; then
  hermes cron create "0 9 * * *" --timezone Asia/Jakarta \
    "Run the daily-repo-check skill for this repository and report the result." \
    --skill daily-repo-check --name "kaggle-compe morning check" --workdir "$REPO"
  echo "Scheduled jobs run inside the Hermes gateway. Keeping it running in the background:"
  hermes gateway install || echo "Run 'hermes gateway' yourself when you want the jobs to run."
fi

step "Done"
echo "Start Hermes from the repo so it reads AGENTS.md:"
echo "  cd \"$REPO\" && hermes"
echo "Then try:  /careful-engineer run the tests and tell me what's failing"
