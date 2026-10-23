#!/usr/bin/env bash
# Open the AI Office (after setup.sh has run once):  bash start-office.sh
cd "$(dirname "$0")"
curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1 || { (ollama serve >/dev/null 2>&1 &); sleep 3; }
exec .venv/bin/python -m office
