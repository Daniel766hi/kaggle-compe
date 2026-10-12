#!/usr/bin/env python3
"""Claude Code Stop hook: send the agent through the completion audit before it ends.

Installed in the trial container. When Claude Code is about to finish, this hook blocks the
stop and hands back the audit checklist, up to the number of times in ``audit_max_rounds``
(default 1). The agent then checks its work in the same session and stops normally. Standard
library only.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Written by the harness for each trial (see harness.STATE_DIR).
STATE_DIR = Path(os.environ.get("CHI_PILOT_STATE_DIR", "/logs/agent/chi-pilot"))


def decide(rounds_done: int, max_rounds: int, audit: str) -> dict | None:
    """Return the hook's JSON reply, or None to let the agent stop."""
    if not audit.strip() or rounds_done >= max_rounds:
        return None
    return {"decision": "block", "reason": audit}


def _read_int(path: Path, default: int) -> int:
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return default


def main() -> int:
    sys.stdin.read()  # the hook input is not needed: the round counter decides
    max_rounds = _read_int(STATE_DIR / "audit_max_rounds", 1)
    rounds_done = _read_int(STATE_DIR / "audit_rounds", 0)
    try:
        audit = (STATE_DIR / "audit.md").read_text(encoding="utf-8")
    except OSError:
        audit = ""

    reply = decide(rounds_done, max_rounds, audit)
    if reply is None:
        return 0
    try:
        (STATE_DIR / "audit_rounds").write_text(str(rounds_done + 1))
    except OSError:
        # Without a counter the hook could block forever; let the agent stop instead.
        return 0
    json.dump(reply, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
