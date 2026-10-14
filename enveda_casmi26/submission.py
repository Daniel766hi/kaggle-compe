"""Check an Enveda CASMI 2026 `submission.csv` against the rules on the Evaluation page.

    python -m enveda_casmi26.submission TEST.parquet SUBMISSION.csv

Every test `molecule_id` exactly once, no nulls, at most 25 `;`-separated SMILES per row.
"""

import sys

import pandas as pd

MAX_GUESSES = 25


def validate(sub, molecule_ids):
    """Return a list of problems; empty means the file would be accepted."""
    problems = []
    if list(sub.columns[:2]) != ["molecule_id", "smiles"] or len(sub.columns) != 2:
        return [f"columns must be molecule_id,smiles, got {list(sub.columns)}"]
    if sub.empty:
        return ["submission is empty"]
    if sub.isna().any().any():
        problems.append("null values present")
    dup = sub.molecule_id[sub.molecule_id.duplicated()].unique()
    if len(dup):
        problems.append(f"{len(dup)} repeated molecule_id, e.g. {list(dup[:3])}")
    expected = set(molecule_ids)
    missing, extra = expected - set(sub.molecule_id), set(sub.molecule_id) - expected
    if missing:
        problems.append(f"{len(missing)} test molecules missing, e.g. {sorted(missing)[:3]}")
    if extra:
        problems.append(f"{len(extra)} unknown molecule_id, e.g. {sorted(extra)[:3]}")
    n = sub.smiles.fillna("").astype(str).str.split(";").str.len()
    if (n > MAX_GUESSES).any():
        problems.append(f"{int((n > MAX_GUESSES).sum())} rows with more than {MAX_GUESSES} guesses")
    return problems


def main(argv):
    test = pd.read_parquet(argv[0], columns=["molecule_id"])
    problems = validate(pd.read_csv(argv[1]), test.molecule_id.unique())
    print("valid" if not problems else "\n".join(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
