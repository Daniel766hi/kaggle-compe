# MBG paper — working folder

| File | What it is |
|---|---|
| `MBG_paper.pdf` | **The paper.** Two-column LaTeX layout (A4, Times, numbered references), same structure as the author's SLR manuscript. Built from the final model run. |
| `latex/MBG_paper.tex` | LaTeX source (uploadable to Overleaf together with `latex/figures/`). |
| `build_paper_latex.py` | Rebuilds the paper: `python build_paper_latex.py`. Every number in the abstract, Data, Results, Discussion and Conclusion is read from `model/outputs/`, so text and tables always match. Needs pdflatex with TikZ. |
| `paper_discussion.py` | Sections 6–8 (Discussion, Limitations, Conclusion), executed by the builder. |
| `model/` | Vensim model + Python pipeline (see `model/README.md`). |
| `model/data/VERIFICATION.md` | How each input was verified, what changed, and what to check yourself. |
| `literature_reading_list.md` | Sources with links. |
| `build_manuscript.py`, `Manuscript_DRAFT.docx`, `Methods_section_DRAFT.docx`, `MBG_SD_ML_paper_template.docx` | Earlier Word drafts; superseded by the LaTeX paper. |

## Before you submit

1. Read the whole paper and change any wording that does not sound like you. You must be able to explain every equation and result.
2. Open the sources listed under "Residual check" in `model/data/VERIFICATION.md` (BPS tables, the elasticity paper's full text) and confirm the figures.
3. Check every reference against the original (authors, year, volume, pages, DOI). The IPB article's authors are not yet listed.
4. Keep the "Use of AI tools" declaration; journals require it.
5. Choose the journal and adapt the template (see the venue list from earlier in this project).

## Rebuilding after a change

```bash
cd model && python run_all.py 5000      # about 5 hours at TIME STEP 0.03125
cd .. && python build_paper_latex.py
```
