"""Harbor harness for chi-pilot: Claude Code plus χ-Bench workflow guidance.

On top of the stock ``claude-code`` harness it:

1. detects the task's track (provider PA, payer UM, care management) from the instruction and
   appends the matching operating guide to Claude Code's system prompt;
2. installs ``hb-search``, a ranked search over the Managed-Care Operations Handbook;
3. registers a Stop hook that makes the agent run a track-specific completion audit, in the
   same session, before it ends (one round by default);
4. defaults to high reasoning effort.

It runs one Claude Code session, so Harbor's trajectory, token and cost accounting are
unchanged. Settings read from the host environment (``.env``):

- ``CHI_PILOT_AUDIT_ROUNDS``: completion audits per task (default 1, 0 disables them).
- ``CHI_PILOT_EFFORT``: Claude Code effort when no ``reasoning_effort`` kwarg is given
  (default ``high``).
- ``CHI_PILOT_CLAUDE_CODE_VERSION``: pin the Claude Code release (default: latest).
"""

from __future__ import annotations

import base64
import json
import os
import shlex
from pathlib import Path
from typing import TYPE_CHECKING

from harbor.agents.installed.claude_code import ClaudeCode
from harbor.models.trial.paths import EnvironmentPaths

from . import AGENT_NAME
from .domains import detect_domain
from .playbooks import audit_prompt, system_prompt

if TYPE_CHECKING:
    from harbor.environments.base import BaseEnvironment
    from harbor.models.agent.context import AgentContext

PACKAGE_DIR = Path(__file__).resolve().parent
# Static scripts, written as root at install time.
BIN_DIR = "/installed-agent/chi-pilot"
# Per-trial state, written as the agent user. Lives under /logs/agent so it is kept with the
# trial's logs for debugging.
STATE_DIR = (EnvironmentPaths.agent_dir / "chi-pilot").as_posix()
CLAUDE_CONFIG_DIR = (EnvironmentPaths.agent_dir / "sessions").as_posix()

_EFFORT_CHOICES = ("low", "medium", "high", "xhigh", "max")

_PYTHON_WRAPPER = """\
#!/bin/sh
for PY in python3 /workspace/.venv/bin/python python; do
  if command -v "$PY" >/dev/null 2>&1; then exec "$PY" {script} "$@"; fi
done
echo "chi-pilot: no python interpreter found" >&2
exit 127
"""

# Claude Code treats a Stop hook exiting with status 2 as "block and show stderr", so a broken
# hook could keep the agent from ever stopping. This wrapper always exits 0.
_STOP_HOOK_WRAPPER = """\
#!/bin/sh
for PY in python3 /workspace/.venv/bin/python python; do
  if command -v "$PY" >/dev/null 2>&1; then "$PY" {script}; exit 0; fi
done
exit 0
"""


def _write_command(path: str, content: str, mode: str = "644") -> str:
    """Shell command that writes ``content`` to ``path`` without any quoting hazards."""
    data = base64.b64encode(content.encode("utf-8")).decode("ascii")
    quoted = shlex.quote(path)
    return f"printf '%s' {data} | base64 -d > {quoted} && chmod {mode} {quoted}"


def stop_hook_settings() -> dict:
    return {
        "hooks": {
            "Stop": [
                {"hooks": [{"type": "command", "command": f"{BIN_DIR}/stop-hook", "timeout": 30}]}
            ]
        }
    }


class ChiPilotHarness(ClaudeCode):
    @staticmethod
    def name() -> str:
        return AGENT_NAME

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._version is None:
            self._version = os.environ.get("CHI_PILOT_CLAUDE_CODE_VERSION") or None
        if "reasoning_effort" not in self._resolved_flags:
            effort = os.environ.get("CHI_PILOT_EFFORT", "high")
            if effort not in _EFFORT_CHOICES:
                raise ValueError(f"CHI_PILOT_EFFORT must be one of {_EFFORT_CHOICES}, not {effort!r}")
            self._resolved_flags["reasoning_effort"] = effort
        self._audit_rounds = max(int(os.environ.get("CHI_PILOT_AUDIT_ROUNDS", "1")), 0)
        # A user-supplied --append-system-prompt is kept and placed after the guide.
        self._user_system_prompt = self._resolved_flags.get("append_system_prompt") or ""

    async def install(self, environment: BaseEnvironment) -> None:
        await super().install(environment)
        commands = [
            f"mkdir -p {BIN_DIR}",
            _write_command(f"{BIN_DIR}/hb_search.py", (PACKAGE_DIR / "hb_search.py").read_text()),
            _write_command(f"{BIN_DIR}/stop_hook.py", (PACKAGE_DIR / "stop_hook.py").read_text()),
            _write_command(
                f"{BIN_DIR}/hb-search",
                _PYTHON_WRAPPER.format(script=f"{BIN_DIR}/hb_search.py"),
                mode="755",
            ),
            _write_command(
                f"{BIN_DIR}/stop-hook",
                _STOP_HOOK_WRAPPER.format(script=f"{BIN_DIR}/stop_hook.py"),
                mode="755",
            ),
            f"ln -sf {BIN_DIR}/hb-search /usr/local/bin/hb-search",
        ]
        await self.exec_as_root(environment, command=" && ".join(commands))

    def _trial_files(self, instruction: str) -> tuple[str, dict[str, str]]:
        domain = detect_domain(instruction)
        prompt = system_prompt(domain)
        if self._user_system_prompt:
            prompt = f"{prompt}\n{self._user_system_prompt}"
        files = {
            f"{STATE_DIR}/domain": domain,
            f"{STATE_DIR}/system_prompt.md": prompt,
            f"{STATE_DIR}/audit.md": audit_prompt(domain),
            f"{STATE_DIR}/audit_max_rounds": str(self._audit_rounds),
            f"{STATE_DIR}/audit_rounds": "0",
            f"{CLAUDE_CONFIG_DIR}/settings.json": json.dumps(stop_hook_settings(), indent=2),
        }
        return domain, files

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        domain, files = self._trial_files(instruction)
        self.logger.info(f"chi-pilot: track={domain}, audit rounds={self._audit_rounds}")
        commands = [f"mkdir -p {STATE_DIR} {CLAUDE_CONFIG_DIR}"]
        commands += [_write_command(path, content) for path, content in files.items()]
        await self.exec_as_agent(environment, command=" && ".join(commands))

        # CLI flag values are inserted into the command unquoted, so pass the prompt through a
        # file read by the shell rather than inline.
        self._resolved_flags["append_system_prompt"] = f'"$(cat {STATE_DIR}/system_prompt.md)"'
        await super().run(instruction, environment, context)
