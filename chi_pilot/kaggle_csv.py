"""Build the Kaggle submission file (task_id,reward) from χ-Bench trial results.

    python -m chi_pilot.kaggle_csv --trials <chi-bench>/logs/submissions/<id> \\
        --data-root <chi-bench>/data --out submission.csv

Every public task gets exactly one row. The reward comes from the trial's
``verifier/reward.json`` (falling back to ``result.json``'s verifier block); a task with no
finished trial gets 0. When a task has several trials, the earliest one counts (pass@1).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

DOMAIN_TASK_DIRS = ("prior_auth_provider/tasks", "prior_auth_um/tasks", "care_management/tasks")


def public_task_ids(data_root: Path) -> list[str]:
    ids = []
    for rel in DOMAIN_TASK_DIRS:
        task_dir = data_root / rel
        if not task_dir.is_dir():
            raise FileNotFoundError(f"missing task directory: {task_dir}")
        ids += [p.name for p in task_dir.iterdir() if p.is_dir()]
    return sorted(ids)


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def trial_reward(trial_dir: Path, result: dict) -> int:
    reward_file = _read_json(trial_dir / "verifier" / "reward.json")
    if reward_file is not None and "reward" in reward_file:
        value = reward_file["reward"]
    else:
        verifier = result.get("verifier_result") or {}
        value = (verifier.get("rewards") or {}).get("reward", verifier.get("reward", 0))
    try:
        return 1 if float(value) >= 1.0 else 0
    except (TypeError, ValueError):
        return 0


def collect_rewards(trials_root: Path) -> dict[str, int]:
    """Map task id to the reward of its earliest trial."""
    first: dict[str, tuple[str, int]] = {}
    for result_path in trials_root.rglob("result.json"):
        result = _read_json(result_path)
        if result is None or not isinstance(result.get("verifier_result"), dict):
            continue  # run-level aggregate, or a trial that never reached the verifier
        task_id = result.get("task_name") or str(result.get("trial_name", "")).split("__")[0]
        if not task_id:
            continue
        started = str(result.get("started_at") or "")
        reward = trial_reward(result_path.parent, result)
        if task_id not in first or started < first[task_id][0]:
            first[task_id] = (started, reward)
    return {task_id: reward for task_id, (_, reward) in first.items()}


def build_rows(task_ids: list[str], rewards: dict[str, int]) -> list[tuple[str, int]]:
    return [(task_id, rewards.get(task_id, 0)) for task_id in task_ids]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trials", type=Path, required=True, help="directory holding trial results")
    parser.add_argument("--data-root", type=Path, required=True, help="χ-Bench data/ directory")
    parser.add_argument("--out", type=Path, default=Path("submission.csv"))
    args = parser.parse_args(argv)

    task_ids = public_task_ids(args.data_root)
    rewards = collect_rewards(args.trials)
    missing = [t for t in task_ids if t not in rewards]
    extra = sorted(set(rewards) - set(task_ids))
    rows = build_rows(task_ids, rewards)

    with args.out.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["task_id", "reward"])
        writer.writerows(rows)

    passed = sum(r for _, r in rows)
    print(f"wrote {args.out}: {len(rows)} tasks, {passed} passed, pass@1 = {passed / len(rows):.3f}")
    if missing:
        print(f"warning: {len(missing)} tasks have no verified trial and count as 0:", file=sys.stderr)
        for task_id in missing:
            print(f"  {task_id}", file=sys.stderr)
    if extra:
        print(f"note: ignored {len(extra)} trials for tasks outside the public set", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
