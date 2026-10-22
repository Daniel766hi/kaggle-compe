# Second writeup: planning notes (case-solution-design stages, condensed)

Frame. Key question: is there a movement capacity that matters for skill players, is measurable from
tracking, and is invisible to the Combine? Constraints as writeup 1 (<= 2,000 words, < 10 visuals,
public notebook, CC BY-NC data). Must not repeat writeup 1 (straight-line A-S engine) or the public
"Measure the Athlete, Not the Drill" work (COD stability).

Diagnose. Writeup 1 showed straight-line speed carries over but does not separate NFL outcomes.
Route breaks in real games are rounded turns, often after the throw (checked on raw traces), so
event-based "cut" detection missed most of them -> switched to a frame-level physical quantity
(centripetal acceleration), which needs no event detection.

Options considered: (1) cut detection + angle-velocity trade-off residual (dropped: misses rounded
breaks); (2) turning envelope / g-g diagram (chosen); (3) drill-to-route matching (kept as a test);
(4) play-level break sharpness vs separation (dropped: negative within-player link, likely tight
coverage forcing harder adjustments - ambiguous, not actionable within the word limit).

Tests (all in notebooks/nfl_bdb2027_turning_engine.py): split-half reliability, stabilisation by
games, 25 Combine-vs-game partial correlations with BH-FDR, 8 drill-to-route matches, 18 outcome
tests with BH-FDR, ball-in-hand plays excluded from the envelope.

Weakest point: outcome links do not survive FDR (min q 0.32). Answer: stated plainly; direction
consistent across three outcomes; framed as a lead for teams to confirm with more data.
