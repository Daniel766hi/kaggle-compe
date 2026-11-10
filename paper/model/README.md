# MBG poultry model: system dynamics + machine-learning scenario discovery

Model and analysis pipeline behind `../MBG_paper.pdf`. Every number in the paper is read from
`outputs/` by `../build_paper_latex.py`. Inputs and their sources: `data/VERIFICATION.md`.
Details of the final run: `outputs/RUN_INFO.txt`.

## Files

| File | Purpose |
|---|---|
| `mbg_poultry.mdl` | Vensim model: MBG roll-out and kitchen suspensions, menu and school-holiday rules, layer and broiler sectors, feed, prices, policy levers. Every constant has a comment giving its source. Opens in Vensim PLE (equations only; the diagram view is empty, and the paper's diagrams are drawn in LaTeX). |
| `common.py` | Uncertainty ranges, policies, outcome indicators, run helpers; also a faster evaluation of lookup tables (identical results). |
| `vector_sim.py` | Runs many scenarios together in one Euler integration (same update as PySD). The ensemble checks it against ordinary PySD runs before use (`outputs/vector_equivalence.csv`). |
| `seasonal_adjustment.py` | Idul Fitri and calendar seasonality estimated on pre-programme prices (2007–2023); seasonally adjusts the calibration series. |
| `fit_suspensions.py` | Fits the suspension hazard and reinstatement time to BGN's suspension figures. |
| `fit_rollout.py` | Fits the S-shaped roll-out to BGN counts of operational kitchens (`data/mbg_rollout_observed.csv`). |
| `s02_validation.py` | Extreme-condition tests (A1–A6), integration-error test (B1), parameter-recovery test, calibration, identifiability profile, behaviour reproduction. |
| `s01_baseline.py` | Baseline run with and without the programme. |
| `s03_ensemble.py` | 5,000 Latin Hypercube scenarios × 6 policies, each with a no-programme counterfactual (paired design). |
| `check_time_step.py` | Test B2: all ensemble scenarios rerun at half the time step for four policies. |
| `s04_scenario_discovery.py` | Classifier benchmark, decision-tree rules, SHAP, PRIM, one-at-a-time comparison, early-warning classifier. |
| `s05_policy_comparison.py` | Spike probabilities (Wilson CI), Wilcoxon (Holm), rank-biserial effect sizes, McNemar, Friedman, alternative spike definitions. |
| `parameter_sheet.py` | Writes `data/parameter_sheet.csv` (the parameter appendix). |
| `fetch_wfp_prices.py` | Downloads WFP/HDX retail prices and builds the national price index. |
| `run_all.py` | Runs the pipeline in order; `--from STEP` starts at a later step. |

## Setup and run

```bash
pip install -r requirements.txt
python run_all.py 5000                          # full pipeline
python run_all.py 5000 --from s03_ensemble.py   # ensemble onwards, about 30 minutes on 4 cores
```

If `pip install pysd` fails on `odfpy`:

```bash
pip install --no-deps pysd && pip install parsimonious xarray lxml regex portion progressbar2 black chardet openpyxl netCDF4
```

The slowest step is the calibration in `s02_validation.py` (about 2 hours before the lookup
speed-up in `common.py`; not re-timed since). The ensemble itself takes about 3 minutes.

## Modelling choices to be able to defend

- **Counterfactual outcome:** price effects are *with programme − same scenario without programme*,
  so feed shocks, outbreaks and seasons that would raise prices anyway are not attributed to MBG.
- **Programme priority:** kitchens are served before households when stock is short.
- **Price formation:** adjusts toward a price set by inventory coverage and pulled toward unit cost
  plus a normal margin, capped by `Maximum relative price` (imports, substitutes, market operations).
- **Cooperative sourcing (P2)** changes procurement cost only.
- **Spike** = programme-attributable rise above 10 percentage points in either commodity;
  `s05` reports results for 5–20 points and for sustained spikes.
- **PRIM density target** = halfway between the spike base rate and 1.
- **National aggregation:** no regional detail (stated as a limitation).
