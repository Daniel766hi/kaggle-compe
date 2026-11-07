# MBG paper — working folder

| File | What it is |
|---|---|
| `Manuscript_DRAFT.docx` | Full manuscript draft. Introduction and Methodology are draft wording (rewrite in your own words); literature review is an outline; Results fill in automatically after your final run; Discussion/Conclusion are yours. Appendices A (all model equations) and B (parameters) included. |
| `Manuscript_DRAFT_layout_DEMO.docx` | Same, filled with **demo outputs from placeholder parameters**, to show the final layout. Every table/figure is stamped DEMO. **Never submit or quote it.** |
| `build_manuscript.py` | Rebuilds the manuscript. `python build_manuscript.py` after your real run fills Results from `model/outputs/`. |
| `Methods_section_DRAFT.docx` | Earlier stand-alone methods draft (now merged into the manuscript). |
| `MBG_SD_ML_paper_template.docx` | Original section-by-section guide. |
| `literature_reading_list.md` | Sources to read, with links and search strings. |
| `model/` | Vensim model + Python pipeline (see `model/README.md`). |

## Path to submission
1. Export prices from Panel Harga Pangan → `model/data/raw_prices_TEMPLATE.csv` format → `python model/prepare_price_data.py file.csv`.
2. Fill `model/data/parameter_sheet.csv`; update the `.mdl` and the ranges in `model/common.py`.
3. `cd model && python s02_validation.py` (calibration and fit), then set `DEMO = False` in `common.py` and run `python run_all.py 5000`.
4. `python build_manuscript.py` → Results filled.
5. Read the sources and write Section 2. Write the Results descriptions, Section 5, Section 6 and the Abstract findings.
6. Rewrite all draft text in your own words; verify every citation; remove the red guidance; write the AI-use declaration.
