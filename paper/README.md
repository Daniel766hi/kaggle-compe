# MBG paper

| File | What it is |
|---|---|
| `MBG_paper.pdf` | **The paper.** Two-column LaTeX layout (A4, Times, numbered references), built from the final model run. |
| `latex/MBG_paper.tex`, `latex/figures/` | LaTeX source and figures (can be uploaded to Overleaf as they are). |
| `build_paper_latex.py` | Rebuilds the paper: `python build_paper_latex.py`. Every number in the text and tables is read from `model/outputs/`, so text and results always match. Needs pdflatex with TikZ and adjustbox. |
| `paper_discussion.py` | Sections 6–8 (Discussion, Limitations, Conclusion), executed by the builder. |
| `model/` | Vensim model and Python pipeline (see `model/README.md`). |
| `model/data/VERIFICATION.md` | How each input was verified and what to check yourself. |
| `literature_reading_list.md` | Sources with links. |
| `archive/` | Superseded Word drafts and their builder; kept for reference only, not maintained. |

## Before you submit

1. Read the whole paper and change any wording that does not sound like you. You must be able to explain every equation and result.
2. Open the sources listed under "Residual check" in `model/data/VERIFICATION.md` (BPS tables, the elasticity paper's full text) and confirm the figures.
3. Check every reference against the original (authors, year, volume, pages, DOI). The IPB article's authors are not yet listed.
4. Read and, where relevant, cite the closely related MBG studies listed at the end of `literature_reading_list.md`.
5. Fill in the journal's declarations (funding, competing interests, data availability, use of AI tools) in its submission form or template; the paper itself no longer contains them.
6. Choose the journal and adapt the template.

## Rebuilding after a change

```bash
cd model && python run_all.py 5000
cd .. && python build_paper_latex.py
```
