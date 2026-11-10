# Data

How each input was verified, what changed and what to check yourself: `VERIFICATION.md`.

| File | Content | Source |
|---|---|---|
| `raw/wfp_idn_eggs_chicken_extract.csv`, `raw/SOURCE.txt` | Raw WFP retail prices (eggs, chicken), unchanged | WFP via HDX, CC BY-IGO |
| `wfp_national_monthly.csv`, `wfp_national_monthly_long.csv` | National monthly price index (median of market relatives), 2023–2026 and 2007–2026 | built by `../fetch_wfp_prices.py` |
| `historical_prices.csv` | Calibration series (January 2024 – October 2026) | as above |
| `outliers_removed.csv` | Outliers removed before seasonal estimation | `../seasonal_adjustment.py` |
| `seasonal_factors.csv` | Monthly and Idul Fitri seasonal factors | `../seasonal_adjustment.py` |
| `mbg_rollout_observed.csv` | Operational SPPG counts with the URL of each source | BGN releases and press reports of BGN statements |
| `rollout_fit.csv` | Fitted versus observed SPPG counts | `../fit_rollout.py` |
| `calibrated_parameters.csv` | Estimated investment sensitivities, used by every run | `../s02_validation.py` |
| `parameter_sheet.csv` | Every model constant with value, units and source | `../parameter_sheet.py` |

Record an access date for every source you add, and keep raw downloads unchanged in `raw/`.
