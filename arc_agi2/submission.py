"""Check and score an ARC-AGI-2 `submission.json` offline.

    python -m arc_agi2.submission CHALLENGES.json SUBMISSION.json [SOLUTIONS.json]

A submission maps every task id to one dict per test input, each holding `attempt_1` and
`attempt_2` grids. The score is the share of test outputs matched exactly by either attempt.
"""

import json
import sys


def _is_grid(g):
    return (isinstance(g, list) and 0 < len(g) <= 30
            and all(isinstance(r, list) and 0 < len(r) <= 30 and len(r) == len(g[0]) for r in g)
            and all(isinstance(v, int) and 0 <= v <= 9 for r in g for v in r))


def validate(challenges, submission):
    """Return a list of problems; empty means the file matches the required schema."""
    problems = []
    missing = sorted(set(challenges) - set(submission))
    extra = sorted(set(submission) - set(challenges))
    if missing:
        problems.append(f"{len(missing)} task ids missing, e.g. {missing[:3]}")
    if extra:
        problems.append(f"{len(extra)} unknown task ids, e.g. {extra[:3]}")
    for tid, task in challenges.items():
        preds = submission.get(tid)
        if preds is None:
            continue
        if not isinstance(preds, list) or len(preds) != len(task["test"]):
            problems.append(f"{tid}: expected {len(task['test'])} predictions")
            continue
        for i, p in enumerate(preds):
            for a in ("attempt_1", "attempt_2"):
                if not isinstance(p, dict) or a not in p:
                    problems.append(f"{tid}[{i}]: missing {a}")
                elif not _is_grid(p[a]):
                    problems.append(f"{tid}[{i}].{a}: not a 1-30 x 1-30 grid of ints 0-9")
    return problems


def score(submission, solutions):
    """Fraction of test outputs where attempt_1 or attempt_2 equals the solution exactly."""
    hit = total = 0
    for tid, outs in solutions.items():
        preds = submission.get(tid, [])
        for i, truth in enumerate(outs):
            total += 1
            p = preds[i] if i < len(preds) else {}
            hit += any(p.get(a) == truth for a in ("attempt_1", "attempt_2"))
    return hit / total if total else 0.0


def main(argv):
    challenges, submission = (json.load(open(p)) for p in argv[:2])
    problems = validate(challenges, submission)
    print("valid" if not problems else "\n".join(problems))
    if len(argv) > 2:
        print(f"score {score(submission, json.load(open(argv[2]))):.4f}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
