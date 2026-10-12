"""Offline tests for the ARC-AGI-2 submission checker."""

from arc_agi2.submission import score, validate

CHALLENGES = {"t1": {"train": [], "test": [{"input": [[0]]}, {"input": [[1]]}]},
              "t2": {"train": [], "test": [{"input": [[2]]}]}}
SOLUTIONS = {"t1": [[[1, 2]], [[3]]], "t2": [[[4]]]}


def sub(**over):
    s = {"t1": [{"attempt_1": [[1, 2]], "attempt_2": [[0]]},
                {"attempt_1": [[0]], "attempt_2": [[0]]}],
         "t2": [{"attempt_1": [[9]], "attempt_2": [[4]]}]}
    s.update(over)
    return s


def test_valid_submission_and_score():
    assert validate(CHALLENGES, sub()) == []
    assert score(sub(), SOLUTIONS) == 2 / 3  # t1[0] via attempt_1, t2 via attempt_2


def test_missing_task_and_wrong_count_are_reported():
    s = sub()
    del s["t2"]
    assert any("missing" in p for p in validate(CHALLENGES, s))
    assert validate(CHALLENGES, sub(t2=[])) == ["t2: expected 1 predictions"]


def test_bad_grids_are_reported():
    bad = sub(t2=[{"attempt_1": [[10]], "attempt_2": [[1], [1, 2]]}])
    problems = validate(CHALLENGES, bad)
    assert len(problems) == 2 and all("not a" in p for p in problems)
    assert validate(CHALLENGES, sub(t2=[{"attempt_1": [[1]]}])) == ["t2[0]: missing attempt_2"]
