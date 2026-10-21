# Stage 2: Diagnosis (from the data)

Issue tree: "Why do Combine numbers transfer weakly to NFL play?"
1. Measurement: does the Combine number measure one ability?
   - 40 time ~ top speed S0 (within-position r -0.82); blind to tau (r -0.08). 10-yd split also tracks S0 (r -0.60), not tau (+0.02).
   - Tracked A0/tau less repeatable across attempts (test-retest 0.67 / 0.52) than S0 (0.96).
2. Context: is the same ability expressed in games?
   - Game A-S profiles reliable (split-half 0.96 S0, 0.93 A0, 0.97 braking).
   - Carry-over within position: S0 0.41-0.58 (not OL); A0 <= 0.24; braking ~0 except DL.
   - Rookies use 82-93% of Combine top speed in games (median by position).
3. Outcome: does engine size drive results?
   - 24 player-level partial correlations (role, weight, draft removed): none survives BH (min q 0.13).
4. Usage: does using the engine drive results?
   - Within-player launch utilization strongly tied to pressure (rushers), separation (receivers), and with opposite sign to pressure allowed (OL).

Root cause: the Combine measures engine *size* (well only for top speed) under drill conditions; NFL
results depend on how much of the engine a player deploys at the snap, which the Combine never sees
(habit U vs Combine metrics: |partial r| <= 0.13).
