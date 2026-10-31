"""Convert a percent-format notebook script (`# %%` cells) to .ipynb next to it.

Usage: python scripts/percent_to_ipynb.py notebooks/name.py [--set NAME=VALUE ...] [--out path.ipynb]

`--set` replaces the first top-level assignment `NAME = ...` in the script, so one source can
produce variants (for example a submission-only copy with `RUN_EXPERIMENT=False`).
"""

import argparse
import json
import re
from pathlib import Path


def convert(source: str) -> dict:
    parts = re.split(r"^# %%(.*)$", source, flags=re.M)
    cells = []
    for marker, body in zip(parts[1::2], parts[2::2]):
        body = body.strip("\n")
        if "[markdown]" in marker:
            text = "\n".join(line[2:] if line.startswith("# ") else line.lstrip("#") for line in body.splitlines())
            cells.append({"cell_type": "markdown", "metadata": {}, "source": text.splitlines(True)})
        else:
            cells.append(
                {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": body.splitlines(True)}
            )
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("script", type=Path)
    parser.add_argument("--set", action="append", default=[], metavar="NAME=VALUE")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    source = args.script.read_text()
    for item in args.set:
        name, value = item.split("=", 1)
        source, count = re.subn(rf"^{re.escape(name)} = .*$", f"{name} = {value}", source, count=1, flags=re.M)
        if not count:
            raise SystemExit(f"{name} is not assigned at top level in {args.script}")

    out = args.out or args.script.with_suffix(".ipynb")
    out.write_text(json.dumps(convert(source), indent=1, ensure_ascii=False))
    print(out)


if __name__ == "__main__":
    main()
