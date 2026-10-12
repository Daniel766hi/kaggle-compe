"""Summarize χ-Bench trial results: per-trial rows, failed checks and headline metrics.

    python -m chi_pilot.results --trials <dir> --label chi-pilot --out <dir>

writes ``trial_summary.csv`` (one row per trial) and ``failed_checks.csv`` (check name counts).
The trials directory holds one sub-directory per track (``pa_provider``, ``pa_um``, ``cm``), as
written by ``cb submission run`` or by an experiment run per track. Only check names are
exported, never judge explanations or trajectories, so the outputs carry no handbook text.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

TRACKS = ("pa_provider", "pa_um", "cm")
FIELDS = (
    "label", "track", "task_id", "attempt", "reward", "fractional_reward",
    "n_failed_checks", "failed_checks", "cost_usd", "tool_calls", "detected_track",
)


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _reward(trial: Path, result: dict) -> int:
    reward_file = _read_json(trial / "verifier" / "reward.json")
    if reward_file is not None and "reward" in reward_file:
        value = reward_file["reward"]
    else:
        verifier = result.get("verifier_result") or {}
        value = (verifier.get("rewards") or {}).get("reward", verifier.get("reward", 0))
    try:
        return 1 if float(value) >= 1.0 else 0
    except (TypeError, ValueError):
        return 0


def _check_name(check) -> str:
    return check if isinstance(check, str) else str((check or {}).get("name", check))


def _tool_calls(trial: Path) -> int | None:
    trajectory = _read_json(trial / "agent" / "trajectory.json")
    if trajectory is None:
        return None
    return sum(len(step.get("tool_calls") or []) for step in trajectory.get("steps") or [])


def summarize_trials(trials_root: Path, label: str) -> list[dict]:
    """One row per verified trial; attempts are numbered per task in start order."""
    found = []
    for result_path in trials_root.rglob("result.json"):
        parts = result_path.relative_to(trials_root).parts
        if "packet" in parts or parts[0] not in TRACKS:
            continue  # packet copies from `cb submission prepare`, or unrelated files
        result = _read_json(result_path)
        if result is None or not isinstance(result.get("verifier_result"), dict):
            continue  # run-level aggregate, or a trial that never reached the verifier
        trial = result_path.parent
        scorecard = _read_json(trial / "verifier" / "scorecard.json") or {}
        failed = [_check_name(c) for c in scorecard.get("failed_checks") or []]
        domain_file = trial / "agent" / "chi-pilot" / "domain"
        found.append({
            "label": label,
            "track": parts[0],
            "task_id": result.get("task_name") or str(result.get("trial_name", "")).split("__")[0],
            "started_at": str(result.get("started_at") or ""),
            "reward": _reward(trial, result),
            "fractional_reward": scorecard.get("fractional_reward"),
            "n_failed_checks": len(failed),
            "failed_checks": ";".join(failed),
            "cost_usd": (result.get("agent_result") or {}).get("cost_usd"),
            "tool_calls": _tool_calls(trial),
            "detected_track": domain_file.read_text().strip() if domain_file.exists() else "",
        })
    found.sort(key=lambda r: (r["track"], r["task_id"], r["started_at"]))
    attempts: Counter = Counter()
    rows = []
    for row in found:
        attempts[row["task_id"]] += 1
        row["attempt"] = attempts[row["task_id"]]
        rows.append({k: row[k] for k in FIELDS})
    return rows


def read_summary(path: Path) -> list[dict]:
    with path.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    for row in rows:
        row["attempt"] = int(row["attempt"])
        row["reward"] = int(row["reward"])
        for key in ("cost_usd", "tool_calls"):
            row[key] = float(row[key]) if row.get(key) not in (None, "") else None
    return rows


def _bootstrap_ci(values: list[int], iters: int = 1000, seed: int = 0) -> tuple[float, float]:
    """Percentile bootstrap 95% CI of the mean, resampling tasks (as in the χ-Bench paper)."""
    if not values:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(rng.choice(values) for _ in range(n)) / n for _ in range(iters))
    return means[int(0.025 * iters)], means[int(0.975 * iters) - 1]


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def metrics(rows: list[dict], track: str | None = None) -> dict:
    """pass@1 (first attempt), its CI, pass^3 when 3 attempts exist, mean cost and tool calls."""
    rows = [r for r in rows if track is None or r["track"] == track]
    by_task: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_task[row["task_id"]].append(row)
    first = [min(trials, key=lambda r: r["attempt"]) for trials in by_task.values()]
    rewards = [r["reward"] for r in first]
    with_three = [sorted(t, key=lambda r: r["attempt"])[:3] for t in by_task.values() if len(t) >= 3]
    lo, hi = _bootstrap_ci(rewards)
    return {
        "n_tasks": len(first),
        "pass_at_1": _mean(rewards),
        "ci_low": lo,
        "ci_high": hi,
        "pass_pow_3": _mean([int(all(r["reward"] for r in t)) for t in with_three])
        if with_three and len(with_three) == len(by_task) else None,
        "mean_cost_usd": _mean([r["cost_usd"] for r in first if r["cost_usd"] is not None]),
        "mean_tool_calls": _mean([r["tool_calls"] for r in first if r["tool_calls"] is not None]),
    }


def failed_check_counts(rows: list[dict]) -> Counter:
    """How many first-attempt trials failed each check."""
    counts: Counter = Counter()
    for row in rows:
        if row["attempt"] == 1 and row["failed_checks"]:
            counts.update(set(row["failed_checks"].split(";")))
    return counts


def write_outputs(rows: list[dict], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "trial_summary.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    with (out_dir / "failed_checks.csv").open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["check", "n_trials"])
        writer.writerows(failed_check_counts(rows).most_common())


def _fmt(value: float | None, pattern: str = "{:.3f}") -> str:
    return "-" if value is None else pattern.format(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trials", type=Path, required=True)
    parser.add_argument("--label", required=True, help="configuration name, e.g. chi-pilot")
    parser.add_argument("--out", type=Path, required=True, help="directory for the CSV files")
    args = parser.parse_args(argv)

    rows = summarize_trials(args.trials, args.label)
    write_outputs(rows, args.out)
    print(f"{len(rows)} trials -> {args.out}/trial_summary.csv, failed_checks.csv")
    for track in (*TRACKS, None):
        m = metrics(rows, track)
        if not m["n_tasks"]:
            continue
        print(
            f"{track or 'overall':12s} tasks={m['n_tasks']:3d} pass@1={_fmt(m['pass_at_1'])} "
            f"[{_fmt(m['ci_low'])}, {_fmt(m['ci_high'])}] pass^3={_fmt(m['pass_pow_3'])} "
            f"cost=${_fmt(m['mean_cost_usd'], '{:.2f}')} tools={_fmt(m['mean_tool_calls'], '{:.1f}')}"
        )
    mismatched = [r for r in rows if r["detected_track"] and r["detected_track"] != r["track"]]
    if mismatched:
        print(f"warning: track detection differs from the task's track in {len(mismatched)} trials",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
