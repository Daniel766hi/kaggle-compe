#!/usr/bin/env bash
# AI Office: one-time setup for macOS and Linux, then it starts the office.
#
#   bash setup.sh
#
# It installs (only what's missing): ffmpeg, Ollama and a free local AI model sized for this
# computer, plus the Python packages in .venv. It asks for your free Pixabay key, saves keys in
# .env (never committed), and opens the office. Safe to run again; it skips what's already done.
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

step "Ollama (the free local AI)"
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

step "Starting the AI Office"
echo "Next time, just run: bash start-office.sh"
exec "$PY" -m office
