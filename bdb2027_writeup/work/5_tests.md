# Stage 5: Tests run (all in notebooks/nfl_bdb2027_combine_engine.py)

- Sprint fits: 412/418 tracked 40s usable, median RMSE 0.20 yd/s; peak tracked speed vs official 40 r = -0.98.
- Reliability: Combine 40 test-retest (S0 .96, A0 .67, tau .52, n 356); game profile split-half
  Spearman-Brown (S0 .96, A0 .93, braking .97).
- Carry-over: within-position Pearson with player bootstrap CIs; robustness after removing weight.
- Games-equivalent: target = profile in games 9+ (229 rookies with 16+ games); residualise on position
  + weight; squared partial r for Combine and for first k games (k = 1..8, same estimator); 500
  player bootstraps -> S0 5.0 games (2.2 to >8), A0 0.2 (0.0-0.9), braking 0.4 (0.0-2.7).
- Outcomes (player level): 24 partial correlations, BH-FDR: none significant (min q 0.13).
- Utilization (play level): player fixed effects, player-clustered SEs; launch window 1 s, pressures
  before 1 s removed; robustness with blitz flag and time to throw.
Weakest point: launch U vs pressure is observational (play design). Answer: within-player design,
launch window precedes outcome, opposite sign for OL shows it is not a generic "busy play" artefact.
