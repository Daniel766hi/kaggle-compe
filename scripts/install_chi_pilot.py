"""Install the chi-pilot harness into a χ-Bench checkout.

    python scripts/install_chi_pilot.py --chi-bench ../chi-bench

Copies ``chi_pilot/`` to ``src/chi_bench/experiment/agents/chi_pilot/`` and registers the
agent name ``chi-pilot`` in the harness registry. Safe to run again after changing the code.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SOURCE = REPO / "chi_pilot"
AGENTS_REL = Path("src/chi_bench/experiment/agents")
IMPORT_PATH = "chi_bench.experiment.agents.chi_pilot.harness:ChiPilotHarness"
REGISTRY_ANCHOR = "IN_TREE_AGENT_IMPORT_PATHS: dict[str, str] = {\n"
ENV_ANCHOR = "AGENT_ENV_VARS: dict[str, tuple[str, ...]] = {\n"
REGISTRY_LINE = f'    "chi-pilot": "{IMPORT_PATH}",\n'
ENV_LINE = '    "chi-pilot": ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_BASE_URL"),\n'


def register(registry_text: str) -> str:
    """Return the registry source with chi-pilot added (unchanged if already there)."""
    if '"chi-pilot"' in registry_text:
        return registry_text
    for anchor, line in ((REGISTRY_ANCHOR, REGISTRY_LINE), (ENV_ANCHOR, ENV_LINE)):
        if anchor not in registry_text:
            raise ValueError(f"registry.py layout changed: cannot find {anchor.strip()!r}")
        registry_text = registry_text.replace(anchor, anchor + line, 1)
    return registry_text


def install(chi_bench: Path) -> Path:
    agents_dir = chi_bench / AGENTS_REL
    registry = agents_dir / "registry.py"
    if not registry.is_file():
        raise FileNotFoundError(f"{registry} not found: is {chi_bench} a χ-Bench checkout?")
    target = agents_dir / "chi_pilot"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(SOURCE, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    registry.write_text(register(registry.read_text()))
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--chi-bench", type=Path, required=True, help="path to the χ-Bench checkout")
    args = parser.parse_args(argv)
    target = install(args.chi_bench.resolve())
    print(f"installed chi-pilot into {target}")
    print("check with: uv run cb agent list   (chi-pilot should be listed as in-tree)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
