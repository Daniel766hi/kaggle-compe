---
name: code-review
description: Review a diff or PR for real bugs, ranked by severity
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [code-review, bugs, quality, pull-requests]
    category: kaggle-compe
    requires_toolsets: [terminal]
    related_skills: [careful-engineer, github-workflow]
---

# Code Review

Find correctness bugs in a change before it ships. Report only findings you can back with a
concrete failure scenario, most severe first.

## When to Use
- "Review my changes", "review PR 12", "is this safe to merge?", or before pushing a large change.

## Procedure
1. **Get the diff.**
   - Local work: `git diff origin/main...HEAD` (and `git diff` for unstaged changes).
   - A PR: `gh pr diff <n>` and `gh pr view <n>` for the description.
2. **Read context, not just the diff.** Open each changed function in full, plus its callers
   (`grep -rn "<function_name>(" .`) and its tests.
3. **Hunt for bugs**, checking each change against:
   - Wrong logic: off-by-one, inverted condition, wrong variable, unhandled `None`/empty input.
   - Data: timezone/date handling, dtype changes, duplicate or dropped rows in merges,
     sorting assumptions, NaN propagation.
   - Error paths: network/file failures, partial failures leaving bad state, retries that
     duplicate side effects (double uploads, double posts).
   - Safety: secrets logged or committed, unvalidated external input, destructive operations.
   - Contracts: changed function signatures or file formats that other code still relies on.
   - Tests: does a test cover the new behaviour? Would it fail if the bug existed?
4. **Verify each candidate.** Write the concrete input → wrong result. If you can, prove it
   with a quick script or a failing test. Drop anything you can't substantiate.
5. **Report** as a numbered list, most severe first:
   `file:line` — one-sentence defect — failure scenario — suggested fix.
   Then, separately and briefly, optional cleanups (simplification, naming, duplication).
   If nothing survives verification, say so plainly.
6. **Fix only if asked.** Then follow the `careful-engineer` workflow for each fix.

## Pitfalls
- Style nitpicks dressed up as bugs. Keep them in the optional section or leave them out.
- Reviewing only the diff lines and missing a broken caller elsewhere.
- Vague findings ("might cause issues"). Every finding needs a concrete scenario.

## Verification
- Every reported bug has a reproducible scenario; confirmed ones have a failing test or script.
