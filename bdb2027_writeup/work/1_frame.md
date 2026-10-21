# Stage 1: Frame

**Key question.** Can the movement "engine" a prospect shows in Combine tracking be expressed in the
same units as his NFL game movement, so that scouts know which part of the engine carries over and
coaches can see, week by week, how much of it a rookie actually uses?

**Situation.** Combine evaluation still rests on stopwatch times (40, 10-yd split, 3-cone, shuttle).
The 2027 data adds 10 Hz tracking of 6,310 Combine drill attempts and 10 Hz game tracking of the
same 510 rookies (2023-2025 seasons).

**Complication.** Published studies find Combine times predict draft slot better than NFL
performance, with modest, position-dependent links (McGee & Burkett 2003; Kuzmits & Adams 2008;
Vincent et al. 2019). A stopwatch time mixes two separate abilities (how hard a player accelerates
and how fast he can eventually go) and says nothing about whether he reaches either on Sundays.
Games-played and starts are confounded with draft capital (Keefer 2017).

**Question.** Build a Combine-to-NFL bridge from physics, not correlations: fit the same two-number
acceleration-speed profile (A0, S0) from the 40-yard dash (Samozino et al. 2016) and from game
tracking (in-situ profile, Morin et al. 2021), then ask (1) does it carry over, (2) is it reliable,
(3) does it add information about NFL outcomes beyond the 40 time and draft slot, (4) how can a
team use it weekly.

**Constraints.** <= 2,000 words; < 10 figures + tables; must use player tracking; public Kaggle
notebook attached; data CC BY-NC 4.0, no redistribution; Open Track; claims backed by data run in
the notebook; cite only verified literature.

**Success criteria (judges' rubric).**
- Football (30%): usable week to week; handles football complexity (position, role, play type,
  draft capital); unique.
- Data science (30%): correct; claims backed by data; appropriate models for ~500 players; innovative.
- Writeup (20%): clear motivation and metric definition, easy to follow.
- Visualisation (20%): accessible, accurate, innovative charts.
