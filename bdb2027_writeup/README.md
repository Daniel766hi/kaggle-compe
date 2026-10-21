# NFL Big Data Bowl 2027 writeup: "How Many NFL Games Is the Combine Worth?"

- `writeup.md`: the writeup text (about 1,870 words with references; 5 figures + 2 tables, within the
  2,000-word / under-10-visuals limit).
- `figures/`: the five figures and the cover image, produced by the notebook and `make_cover.py`.
- `work/`: planning notes (frame, diagnosis, options, scoring, tests, use, Q&A).
- Literature survey behind the ideas: `../reports/NFL Combine tracking literature.md`.

Code:
- `../nfl_bdb2027/`: movement-profile functions (tested in `../tests/test_nfl_bdb2027.py`).
- `../notebooks/nfl_bdb2027_combine_engine.py`: the full analysis (jupytext). On Kaggle it reads the
  competition data directly; locally set `DATA_ROOT` to a folder with the competition CSVs.
- Publish to Kaggle: `python scripts/push_notebooks.py nfl-bdb-2027` (private) and add `--public`
  when ready; the package code is pasted into the notebook automatically.

The competition data is CC BY-NC 4.0 and may not be redistributed, so no data files are committed.

## Submitting (on kaggle.com, cannot be done from the API)
1. Make the notebook public.
2. Competition page → Writeups → New writeup → choose Open Track.
3. Paste `writeup.md`; upload each figure where `![Figure N](...)` appears; set `figures/cover.png`
   as the cover image.
4. Attach the public notebook, then Submit.
