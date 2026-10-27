#!/usr/bin/env bash
# AI Office: one-time setup for macOS and Linux, then it starts the office.
#
#   bash setup.sh
#
# It installs (only what's missing): ffmpeg and the Python packages in .venv. It asks for your free
# Gemini key (the team's brain), your free Cloudflare keys (AI pictures for the videos) and whether
# you want the office on your phone. Without a Gemini key it installs Ollama and a local model.
# Keys are saved in .env (never committed). Safe to run again; it skips what's already done.
set -euo pipefail
cd "$(dirname "$0")"

step() { printf '\n\033[36m== %s\033[0m\n' "$1"; }
have() { command -v "$1" >/dev/null 2>&1; }

step "Python"
have python3 || { echo "Install Python 3.10 or newer from python.org (macOS) or your package manager, then run this again."; exit 1; }
python3 --version
[ -d .venv ] || python3 -m venv .venv
PY=.venv/bin/python
"$PY" -m pip install --quiet --upgrade pip
"$PY" -m pip install --quiet -r requirements.txt

step "ffmpeg (joins video clips)"
if ! have ffmpeg; then
  if [ "$(uname)" = Darwin ]; then
    have brew || { echo "Install Homebrew from brew.sh (or ffmpeg from ffmpeg.org), then run this again."; exit 1; }
    brew install ffmpeg
  elif have apt-get; then
    sudo apt-get update && sudo apt-get install -y ffmpeg fonts-dejavu-core
  else
    echo "Install ffmpeg with your package manager, then run this again."; exit 1
  fi
fi
echo "ffmpeg is ready"

step "Gemini (the team's free AI brain)"
gemini=$("$PY" -m local_env get GEMINI_API_KEY)
while [ -z "$gemini" ]; do
  echo "Opening Google AI Studio: sign in with your Google account and click 'Create API key' (free, no card)."
  (open https://aistudio.google.com/apikey 2>/dev/null || xdg-open https://aistudio.google.com/apikey 2>/dev/null || true)
  read -r -p "Paste your Gemini API key (or press Enter to use a local AI on this computer instead): " gemini
  [ -z "$gemini" ] && break
  if curl -fsS "https://generativelanguage.googleapis.com/v1beta/models?key=$gemini" >/dev/null; then
    "$PY" -m local_env set GEMINI_API_KEY "$gemini"
    echo "Gemini works and the key is saved in .env"
  else
    echo "Google didn't accept that key. Copy it again from aistudio.google.com/apikey."
    gemini=""
  fi
done

if [ -z "$gemini" ]; then
  step "Ollama (a free local AI, instead of Gemini)"
  if ! have ollama; then
    if [ "$(uname)" = Darwin ]; then
      if have brew; then brew install ollama
      else echo "Download Ollama from https://ollama.com/download, open it once, then run this again."; open https://ollama.com/download; exit 1; fi
    else
      curl -fsSL https://ollama.com/install.sh | sh
    fi
  fi
  up() { curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; }
  if ! up; then
    (ollama serve >/dev/null 2>&1 &)
    for _ in $(seq 30); do up && break; sleep 1; done
  fi
  up || { echo "Ollama didn't start. Open the Ollama app, then run this again."; exit 1; }

  if [ "$(uname)" = Darwin ]; then ram_gb=$(( $(sysctl -n hw.memsize) / 1073741824 ))
  else ram_gb=$(( $(awk '/MemTotal/ {print $2}' /proc/meminfo) / 1048576 )); fi
  if [ "$ram_gb" -ge 15 ]; then model=qwen3:8b; elif [ "$ram_gb" -ge 7 ]; then model=qwen3:4b; else model=qwen3:1.7b; fi
  saved=$("$PY" -m local_env get OLLAMA_MODEL)
  [ -n "$saved" ] && model=$saved
  echo "This computer has ${ram_gb} GB of RAM: using $model (download once, a few GB)"
  ollama pull "$model"
  "$PY" -m local_env set OLLAMA_MODEL "$model"
fi

step "Cloudflare (free AI pictures for the videos)"
cf_account=$("$PY" -m local_env get CLOUDFLARE_ACCOUNT_ID)
cf_token=$("$PY" -m local_env get CLOUDFLARE_API_TOKEN)
while [ -z "$cf_account" ] || [ -z "$cf_token" ]; do
  echo "Opening Cloudflare: sign up or log in (free, no card). Then:"
  echo "  1. In the left menu open 'AI' > 'Workers AI' and click 'Use REST API'."
  echo "  2. Copy the Account ID shown there."
  echo "  3. Click 'Create a Workers AI API Token', then 'Create API Token', and copy the token."
  (open https://dash.cloudflare.com/sign-up 2>/dev/null || xdg-open https://dash.cloudflare.com/sign-up 2>/dev/null || true)
  read -r -p "Paste your Account ID (or press Enter to skip and use stock clips): " cf_account
  [ -z "$cf_account" ] && break
  read -r -p "Paste your Workers AI API token: " cf_token
  if curl -fsS -H "Authorization: Bearer $cf_token" "https://api.cloudflare.com/client/v4/accounts/$cf_account/ai/models/search?per_page=1" >/dev/null; then
    "$PY" -m local_env set CLOUDFLARE_ACCOUNT_ID "$cf_account"
    "$PY" -m local_env set CLOUDFLARE_API_TOKEN "$cf_token"
    echo "Cloudflare works: videos will be drawn as AI pictures (about 60 free pictures a day)."
  else
    echo "Cloudflare didn't accept those. Check the Account ID and that the token has the Workers AI permission."
    cf_account=""; cf_token=""
  fi
done

if [ -z "$cf_account" ] || [ -z "$cf_token" ]; then
  step "Pixabay (free stock video clips)"
  key=$("$PY" -m local_env get PIXABAY_API_KEY)
  [ -n "$key" ] || key=$("$PY" -m local_env get PEXELS_API_KEY)  # an older Pexels key still works
  while [ -z "$key" ]; do
    echo "Opening Pixabay: sign up or log in (free). Then open pixabay.com/api/docs and find"
    echo "'key (required)' under Parameters: your key is shown right there (green text)."
    for url in https://pixabay.com/accounts/register/ "https://pixabay.com/api/docs/#api_search_videos"; do
      (open "$url" 2>/dev/null || xdg-open "$url" 2>/dev/null || true)
    done
    read -r -p "Paste your Pixabay API key (or press Enter to skip for now): " key
    if [ -z "$key" ]; then echo "Skipped. Video rendering needs it; run this script again any time."; break; fi
    if curl -fsS "https://pixabay.com/api/videos/?key=$key&q=cat&per_page=3" >/dev/null; then
      "$PY" -m local_env set PIXABAY_API_KEY "$key"
      echo "Key works and is saved in .env"
      if have gh && gh auth status >/dev/null 2>&1; then
        read -r -p "Also save it as a GitHub secret for the daily video runs? (y/n) " yes
        [ "$yes" = y ] && printf '%s' "$key" | gh secret set PIXABAY_API_KEY
      fi
    else
      echo "Pixabay didn't accept that key. Copy it again from pixabay.com/api/docs."
      key=""
    fi
  done
fi

step "Your phone"
phone_mode=$("$PY" -m local_env get OFFICE_PHONE)
if [ -z "$phone_mode" ]; then
  echo "You can open the office on your phone too (this computer has to stay on):"
  echo "  wifi     - when your phone is on the same Wi-Fi"
  echo "  anywhere - from anywhere, even on mobile data (a free Cloudflare tunnel)"
  echo "  no       - only on this computer"
  read -r -p "Which one? (wifi / anywhere / no) " phone_mode
  case "$phone_mode" in wifi|anywhere) ;; *) phone_mode=no ;; esac
  "$PY" -m local_env set OFFICE_PHONE "$phone_mode"
fi
if [ "$phone_mode" = anywhere ] && ! have cloudflared; then
  if have brew; then brew install cloudflared
  else echo "Install cloudflared: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"; fi
fi
[ "$phone_mode" != no ] && echo "When the office opens, click 'Phone' at the top and scan the QR code with your phone."

step "GitHub link (Sync with GitHub, and updates)"
repo=https://github.com/Daniel766hi/kaggle-compe.git
if ! have git; then
  if [ "$(uname)" = Darwin ]; then xcode-select --install 2>/dev/null || true; echo "Install Git (the window that opened), then run this again."
  elif have apt-get; then sudo apt-get install -y git; fi
fi
if have git && [ ! -d .git ]; then
  # A folder from a ZIP: make it a GitHub copy in place. Your .env, plans, chats and videos stay.
  git init --quiet
  git remote add origin "$repo"
  branch=$(git ls-remote --symref origin HEAD | sed -n 's|^ref: refs/heads/\([^[:space:]]*\).*|\1|p')
  git fetch --quiet origin "$branch"
  git symbolic-ref HEAD "refs/heads/$branch"
  git reset --quiet --mixed "origin/$branch"
  # The ZIP may be older than GitHub: take the latest code, keep your own plans in content/.
  git restore --source=HEAD --worktree -- . ":(exclude)content"
  git branch --quiet --set-upstream-to="origin/$branch"
  echo "This folder is now linked to GitHub ($branch)."
fi
if have git && [ -d .git ] && [ -z "$(git config user.email || true)" ]; then
  git config user.name "AI Office"
  git config user.email "ai-office@users.noreply.github.com"
fi

step "Starting the AI Office"
echo "Next time, just run: bash start-office.sh"
exec "$PY" -m office
