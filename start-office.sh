#!/usr/bin/env bash
# Open the AI Office (after setup.sh has run once):  bash start-office.sh
# On your phone too: set OFFICE_PHONE in .env to wifi or anywhere (setup.sh asks), or run
#   bash start-office.sh --phone      (same Wi-Fi)      bash start-office.sh --anywhere   (anywhere)
cd "$(dirname "$0")"
if [ -z "$(.venv/bin/python -m local_env get GEMINI_API_KEY)" ]; then  # the local AI needs Ollama running
  curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1 || { (ollama serve >/dev/null 2>&1 &); sleep 3; }
fi
exec .venv/bin/python -m office "$@"
