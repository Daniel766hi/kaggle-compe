---
name: locate-code
description: Rank the repository's functions and classes against the issue text (BM25 over source code) to find where to edit.
---

# locate-code

Run `scripts/locate.py` once, at the start of a task, with the issue text as the query:

    run_skill_script(skill_name="locate-code", file_path="scripts/locate.py",
                     args={"query": "<issue title and the sentences that describe the bug, including identifiers and error messages>"})

It prints the top functions/classes as `path:line  qualified.name` and the top files.
The ranking is lexical, so treat it as a shortlist: read the top candidates and confirm before editing.
