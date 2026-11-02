---
name: daily-repo-check
description: Morning read-only check of Actions runs and Kaggle data
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [monitoring, github-actions, kaggle, cron, report]
    category: kaggle-compe
    requires_toolsets: [terminal]
    related_skills: [github-workflow, kaggle-datasets]
---

# Daily Repo Check

A read-only health check for the kaggle-compe automation, designed to run as a Hermes cron job
each morning (after the 08:23 WIB dataset update). It diagnoses problems; it does not push,
publish or change secrets.

## When to Use
- Attached to a scheduled cron job, or when the user asks "is everything running?".

## Procedure
1. `cd` to the repo (the cron job sets `--workdir`), then `git fetch origin main --quiet`.
2. **GitHub Actions, last 24 hours:**
   `gh run list --limit 20 --json name,status,conclusion,createdAt,databaseId,url`
   List failed or cancelled runs. For each failure:
   `gh run view <id> --log-failed | tail -60` and extract the real error line.
3. **Disabled schedules:** `gh workflow list --all` and flag any workflow shown as disabled
   (public repos pause schedules after 60 days without commits).
4. **Kaggle datasets:** `kaggle datasets list -m --csv` and note each dataset's last updated
   date. Flag any daily dataset not updated in the last 2 days.
5. **Content queues (optional):** count items waiting for approval in `content/*_queue.json`
   with a short Python one-liner.
6. **Diagnose, don't fix.** For each problem, say the likely cause in one line and the command
   or change that would fix it. If a fix is code, offer to do it in an interactive session.
7. **Report** in at most 10 lines:
   - First line: `All green` or `N problems`.
   - Then one line per problem: what, since when, likely cause, suggested fix, link.

## Pitfalls
- Running the real pipeline or posting content from a cron job. This skill is read-only.
- Long log dumps in the report. Quote only the decisive error line.
- `gh` or `kaggle` not authenticated in the gateway's environment: report that as the problem.

## Verification
- The report names every failed run from the last 24 hours, or says `All green`.
