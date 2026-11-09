# MBG poultry model — system dynamics + ML scenario discovery

Working model and analysis pipeline for the paper *Programme-driven demand shocks in food supply
chains* (template: `../MBG_SD_ML_paper_template.docx`).

> **Status: PRELIMINARY research run.** Parameters are sourced or fitted to data, but 7 inputs
> still need checking against primary documents (`PENDING_VERIFICATION` in `common.py`).
> `outputs/` holds the preliminary 5,000-scenario run (see `outputs/RUN_INFO.txt`); everything in it
> is stamped PRELIMINARY. `outputs_demo/` is the old placeholder demo: never cite it.
> After verifying the inputs, set `PRELIMINARY = False` and run `python run_all.py 5000` again.

## What is here

| File | Purpose |
|---|---|
| `mbg_poultry.mdl` | Vensim model (155 variables): MBG roll-out, kitchen suspensions, egg (layer) sector, broiler sector, feed, prices, policy levers. Opens in Vensim PLE; equations load, **the diagram view is empty — draw the stock-and-flow diagram yourself** (Vensim: *Model → Text Editor* to read equations; drag existing variables onto the view). |
| `common.py` | Uncertainty ranges, policy definitions, outcome indicators, run helper. **Edit ranges here.** |
| `s01_baseline.py` | Baseline vs no-programme run → `fig_baseline_dynamics.png` |
| `s02_validation.py` | Extreme-condition tests, integration-error test, parameter-recovery test; joint egg + chicken calibration (multi-start) on seasonally adjusted data → `data/calibrated_parameters.csv`, which every later run uses |
| `check_time_step.py` | Validation B2: reruns 150 ensemble scenarios at half the time step and checks that spike classification is unchanged |
| `s03_ensemble.py` | Latin Hypercube ensemble; every policy runs on the same scenarios (paired design); each scenario also runs without the programme (counterfactual) |
| `s04_scenario_discovery.py` | Classifier benchmark, CART rules, SHAP, PRIM, one-at-a-time comparison, early-warning classifier |
| `s05_policy_comparison.py` | Spike probabilities (Wilson CI), Wilcoxon signed-rank vs P0 (Holm), rank-biserial effect sizes, McNemar, Friedman, trade-off plot |
| `fetch_wfp_prices.py` | Downloads WFP/HDX retail prices for Indonesia; builds the national monthly index (2023–2026) and long series (2007–2026) |
| `fit_rollout.py` | Fits the S-shaped roll-out (final size, midpoint, steepness) so modelled operational SPPG match BGN counts (`data/mbg_rollout_observed.csv`); writes the values into the `.mdl` |
| `seasonal_adjustment.py` | Estimates Lebaran and calendar seasonality on pre-MBG data (2007–2023) and seasonally adjusts the calibration series |
| `prepare_price_data.py` | Converts raw Panel Harga Pangan prices → `data/historical_prices.csv` |
| `parameter_sheet.py` | Writes `data/parameter_sheet.csv`: every constant with tag, units, range — fill in value/source/justification (becomes your parameter appendix) |
| `run_all.py` | Runs everything in order |

## Setup

```bash
pip install -r requirements.txt
```

If `pip install pysd` fails on `odfpy` (a known build issue on some systems), install PySD without it:

```bash
pip install --no-deps pysd && pip install parsimonious xarray lxml regex portion progressbar2 black chardet openpyxl netCDF4
```

## Run

```bash
python run_all.py 400
```

400 scenarios × 6 policies is a quick test. For the paper use 5,000 scenarios: about 1 h 15 min on 4 cores at TIME STEP 0.125, roughly double at the current 0.0625:

```bash
python run_all.py 5000
```

## Your workflow to turn this into your research

1. **Read the model.** Go through every equation in `mbg_poultry.mdl`. Change any you disagree with. You must be able to explain each one.
2. **Draw the diagrams in Vensim**: causal loop diagram and stock-and-flow diagram (Figures 2–3 of the paper).
3. **Collect data** (see `data/README.md`) and fill in `data/parameter_sheet.csv`.
4. **Update parameters** in the `.mdl` and ranges in `common.py`; justify every one.
5. **Calibrate and validate**: put real prices in `data/historical_prices.csv`, run `s02_validation.py`, check MAPE and Theil statistics.
6. Set `DEMO = False` in `common.py`, run `python run_all.py 5000`.
7. **Interpret** the results yourself and write Sections 4–5.

## Modelling choices you should review (and defend in the paper)

- **Counterfactual outcome:** price effects are measured as *with programme − same scenario without programme*, so feed shocks and outbreaks that would raise prices anyway are not blamed on MBG.
- **Programme priority:** MBG kitchens are served before households when stock is short.
- **Price formation:** anchored on current price, adjusted by inventory coverage and pulled toward unit cost + normal margin; capped by `Maximum relative price` (imports, substitutes, market operations).
- **Cooperative sourcing (P2)** only changes procurement cost in this version. If your interviews suggest it also changes quality/suspensions or farmer investment, add that link.
- **Phased roll-out (P1)** multiplies roll-out duration by 1.75 — choose a value grounded in BGN plans.
- **National aggregation:** no regional detail; state this as a limitation or extend with Vensim subscripts.
- **Spike threshold** = +10 percentage points of programme-attributable price rise (`common.py`). Justify it (e.g. relation to the government reference price, HAP).
