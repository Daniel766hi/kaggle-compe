# Public leaderboard draws, in tasks out of 58

One run of identical files varies by about 1.56 tasks (SD; Dariush Afshar's census of repeated public
draws), so configs are compared by the mean of several draws, not by one score. Score x 58 = tasks
(scores are truncated to two decimals).

| date | ref | config | files_sha256 | public | tasks | note |
|---|---|---|---|---|---|---|
| 2026-10-13 | 57131199 | `agent/locate` (Budget-Fit + locate-code skill) | | 0.20 | 12 | |
| 2026-10-14 | 57186550 | `agent/locate_12b` | | — | — | unhandled error (12B) |
| 2026-10-25 | 57627856 | `agent/verify36` | | — | — | exceeded 12 h runtime |
| 2026-10-28 | 57737224 | `agent/v6_public` (public v6 files, unchanged) | 4a65b9a7 | 0.15 | 9 | its public notebook drew 14; mean of 2 draws 11.5 |
| 2026-10-29 | 57776956 | `agent/locate` draw 2 (same files as 57131199) | 5bf7501e | 0.18 | 11 | mean of 2 draws 11.5 |
| 2026-10-30 | 57815856 | `agent/v6_public` draw 3 | 4a65b9a7 | 0.15 | 9 | v6 mean of 3 draws 10.67 |
| 2026-11-01 | 57877239 | `agent/locate` draw 3 | 5bf7501e | 0.13 | 8 | locate mean of 3 draws 10.33 |
| 2026-11-03 | 57928440 | `agent/v6_public` draw 4 | 4a65b9a7 | 0.18 | 11 | v6 mean of 4 draws 10.75 |
| 2026-11-04 | 57981858 | `agent/locate` draw 4 | 5bf7501e | 0.18 | 11 | locate mean of 4 draws 10.5 |
| 2026-11-05 | 58020346 | `agent/v6_public` draw 5 | 4a65b9a7 | — | — | Kaggle "system error" (scorer side; not counted) |
| 2026-11-06 | 58055327 | `agent/locate` draw 5 | 5bf7501e | 0.18 | 11 | locate mean of 5 draws 10.6 |
| 2026-11-07 | 58089501 | `agent/v6_public` draw 5 (resubmit) | 4a65b9a7 | 0.17 | 10 | v6 mean of 5 draws 10.6 |
| 2026-11-08 | pending | `agent/locate` draw 6 | 5bf7501e | | | |

Reference means from the census (2026-10-22): Budget-Fit 10.00 over 10 draws; Budget-Aware v2 8.71
over 7 later draws (first draw 13).
