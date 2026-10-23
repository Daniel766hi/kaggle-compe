"""Keys and settings for running on your own computer, kept in a `.env` file (never committed).

    python -m local_env set PEXELS_API_KEY abc123
    python -m local_env get OLLAMA_MODEL

The agents and the office read `.env` at start-up. Values already in the environment win, so
GitHub Actions secrets are never overridden.
"""

import os
import sys
from pathlib import Path

ENV_FILE = Path(__file__).with_name(".env")


def read(path=ENV_FILE):
    values = {}
    path = Path(path)
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load(path=ENV_FILE):
    for key, value in read(path).items():
        os.environ.setdefault(key, value)


def save(key, value, path=ENV_FILE):
    path = Path(path)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    lines = [line for line in lines if not line.strip().startswith(f"{key}=")]
    lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "set":
        save(sys.argv[2], sys.argv[3])
    elif len(sys.argv) == 3 and sys.argv[1] == "get":
        print(read().get(sys.argv[2], ""))
    else:
        sys.exit(__doc__)
