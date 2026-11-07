# Data you need to collect

| Data | Where | Used for |
|---|---|---|
| Weekly/daily national egg and broiler-meat prices, 2024–present | Badan Pangan Nasional – Panel Harga Pangan (panelharga.badanpangan.go.id) | `raw_prices_TEMPLATE.csv` → `prepare_price_data.py` → calibration and fit statistics; `Baseline egg price`, `Baseline chicken price` |
| Egg and broiler-meat production (t/year) | BPS – Produksi Telur Ayam Ras / Produksi Daging Ayam Ras; Ditjen PKH *Statistik Peternakan dan Kesehatan Hewan* | `Initial egg production`, `Initial chicken production` |
| Layer population, lay rate, productive life, rearing time | Ditjen PKH statistics; poultry science literature | Egg-sector parameters |
| Household consumption per capita | BPS – SUSENAS (Konsumsi Kalori dan Protein) | Check reference household demand |
| Price elasticities | QUAIDS studies on SUSENAS (see `../../literature_reading_list.md`) | Elasticity ranges |
| SPPG counts over time, beneficiaries, target | BGN official releases | `Target kitchens`, `Beneficiaries per kitchen`, roll-out duration; also a behaviour-reproduction check for the programme sector |
| Menu composition (egg/chicken per portion, portions per week) | BGN menu guidelines; SPPG interviews | `Egg per beneficiary`, `Chicken per beneficiary` |
| Feed (corn) prices | BPS; Panel Harga; Kementan | Feed shock ranges |
| SPPG suspensions | BGN statements | `Base suspension fraction` range |
| DOC supply / hatchery capacity | GPPU (breeders' association), Kementan | `DOC capacity factor`, `Hatchery capacity factor` |

Record the access date for every source. Keep raw downloads unchanged in a `raw/` folder.

`parameter_sheet.csv` lists every constant in the model. Fill in `your_value`, `source`,
`justification`. It becomes the parameter appendix of your paper.
