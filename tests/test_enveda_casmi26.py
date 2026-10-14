"""Offline tests for the Enveda CASMI 2026 submission checker."""

import pandas as pd

from enveda_casmi26.submission import validate


def sub(rows):
    return pd.DataFrame(rows, columns=["molecule_id", "smiles"])


def test_valid():
    assert validate(sub([("m1", "CCO;CCN"), ("m2", "C")]), ["m1", "m2"]) == []


def test_missing_duplicate_and_null():
    problems = validate(sub([("m1", "CCO"), ("m1", None)]), ["m1", "m2"])
    assert any("null" in p for p in problems)
    assert any("repeated" in p for p in problems)
    assert any("missing" in p for p in problems)


def test_too_many_guesses_and_bad_columns():
    assert validate(sub([("m1", ";".join(["C"] * 26))]), ["m1"]) == ["1 rows with more than 25 guesses"]
    assert "columns" in validate(pd.DataFrame({"id": ["m1"]}), ["m1"])[0]
