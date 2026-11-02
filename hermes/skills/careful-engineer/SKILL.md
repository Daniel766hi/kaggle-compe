---
name: careful-engineer
description: Understand, change, verify and report like a senior engineer
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [workflow, coding, debugging, verification]
    category: kaggle-compe
    requires_toolsets: [terminal]
---

# Careful Engineer Workflow

The default way to do any coding, data or automation task: understand the problem, make the
smallest correct change, prove it works, and report honestly.

## When to Use
- Any request to build, fix, change, debug or automate something in a code repository.
- Load it together with a domain skill (e.g. `/careful-engineer /kaggle-datasets add a dataset`).

## Procedure
1. **Orient (read before writing).**
   - `git status`, `git log --oneline -10`, `git branch --show-current`.
   - Read `AGENTS.md`, the README section for the area, and the files you will change.
   - Find an existing example of the same thing and copy its pattern
     (`search_files` / `grep -rn "<name>" .`).
2. **Plan briefly.** For anything more than a one-file change, write a 3-6 line plan: files to
   change, how you'll test it. For a large or risky task, use `/plan` and show the plan first.
3. **Branch.** If on `main`, create a feature branch: `git checkout -b <short-topic>`.
4. **Change in small steps.** Edit only what the task needs. Keep the project's style.
   No unrelated refactors, no new dependencies unless required.
5. **Test.**
   - Bug: reproduce it first (a failing test or command), then fix, then show it passing.
   - Feature: add or extend a test next to the existing ones.
   - Run the fast suite: `python -m pytest -q` (or the project's command from AGENTS.md).
   - For pipelines, run the dry-run mode, never the real publish, unless asked.
6. **Review your own diff.** `git diff` and check: leftover debug prints, secrets, unrelated
   changes, missing error handling at real boundaries (network, files, user input).
7. **Commit.** `git add <specific files>` then a message that says what and why.
   Push only if the user asked: `git push -u origin <branch>`.
8. **Report.** In a few lines: what changed (with `file:line`), what you ran and the result,
   anything not done or still uncertain, and the next step if any.

## Pitfalls
- Guessing at an API or file layout instead of reading it. Check with a command.
- "Fixing" a failing test by deleting, skipping or loosening it. Fix the cause instead.
- Running real uploads/posts/paid API calls to "test". Use dry-run or fakes.
- Claiming success without running anything. If you couldn't run it, say so.
- `git add -A` sweeping in `.env`, build output or data files.
- Asking the user questions the repo already answers.

## Verification
- Tests pass (paste the summary line, e.g. `123 passed`).
- `git status` shows only intended changes; `git diff --cached` contains no secrets.
- The final report states what was verified and what wasn't.
