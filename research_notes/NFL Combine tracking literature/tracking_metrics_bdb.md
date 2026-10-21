# Player-tracking metrics in American football and soccer, and prior NFL Big Data Bowl ideas

Scope: real papers and writeups that link player movement to on-field outcomes, plus Big Data Bowl (BDB) winners and finalists, mapped to what can be computed from 2027 BDB data. That data has 10 Hz x/y/s/a/o/dir for the rookie player only, plus NGS play-level stats such as separation_at_pass_forward, player_get_off, time_to_pressure and pressure_allowed.

Method note: verification relied mostly on web-search result pages, because direct fetches of arxiv.org, operations.nfl.com, sps.nyu.edu and sportsvideo.org failed with DNS errors in this sandbox, and the Kaggle 2027 data page returned only its title. Items marked **[VERIFIED]** appeared with a matching title and author on a real page in search results. Items marked **[UNVERIFIED]** come from memory or have incomplete details. Numbers are given only where a source stated them.

## Football tracking papers: what metric each defines and how it maps to single-rookie 10 Hz data

### Takeaway
Most landmark football tracking papers need all 22 players: Going Deep's ball-carrier model, EHCP, DeepQB, STRAIN's rusher-to-QB distance, and the BDB 2020 CNN. With only the rookie's own track, the transferable parts are:
- self-referenced kinematics: speed and acceleration envelopes, the route shape (Chu et al.), and the rate of closing toward a fixed target such as the line of scrimmage or the expected QB spot (STRAIN-like);
- the NGS play-level outcome stats as response variables.

### Cited Findings
- **Yurko, Matano, Richardson, Granered, Pospisil, Pelechrinis & Ventura (2020), "Going Deep: Models for Continuous-Time Within-Play Valuation of Game Outcomes in American Football with Tracking Data," JQAS 16(2):163–182; arXiv:1906.01760** [VERIFIED]
  - It defines continuous-time within-play expected points and win probability.
  - An LSTM ball-carrier model updates the expected end-of-play yard line from player locations and trajectories, and feeds it into between-play EP/WP models.
  - Sources: [arXiv](https://arxiv.org/pdf/1906.01760); [RePEc JQAS listing](https://ideas.repec.org/a/bpj/jqsprt/v16y2020i2p163-182n5.html)
  - *Single-rookie computability:* low. It needs defender positions. You could approximate a "ball-carrier momentum" feature (speed × heading toward the end zone) for a rookie RB/WR after the catch.
- **Chu, Reyers, Thomson & Wu (2020), "Route Identification in the National Football League," JQAS 16(2):121–132; arXiv:1908.02423** [VERIFIED]
  - Model-based curve clustering of receiver trajectories, using Bernstein-polynomial cluster centers fitted by EM, applied to 33,967 routes on 6,963 passing plays.
  - It recreated the standard route tree without labels, and won the College Division of BDB 2019.
  - Sources: [arXiv](https://arxiv.org/pdf/1908.02423); [RePEc](https://ideas.repec.org/a/bpj/jqsprt/v16y2020i2p121-132n1.html); [SFU News](https://www.sfu.ca/sfunews/stories/2019/04/statistics-students-impress-the-nfl-with-their-moves.html)
  - *Single-rookie computability:* **high**. It only needs the receiver's own x/y path, normalized to the line of scrimmage. Route clusters can condition the kinematic features (for example, the deceleration into the break on curl or out routes versus go routes).
- **Deshpande & Evans (2020), "Expected Hypothetical Completion Probability," JQAS 16(2):85–94; arXiv:1910.12337** [VERIFIED]
  - A Bayesian nonparametric catch-probability model. Unobserved inputs are imputed for untargeted receivers so every receiver can be scored, using BDB 2019 data.
  - Sources: [arXiv](https://arxiv.org/pdf/1910.12337); [RePEc](https://ideas.repec.org/a/bpj/jqsprt/v16y2020i2p85-94n2.html)
  - *Single-rookie computability:* low on its own, because it needs defender distances. The NGS `separation_at_pass_forward` stat stands in for the key separation input.
- **Burke (2019), "DeepQB: Deep Learning with Player Tracking to Quantify Quarterback Decision-Making & Performance," MIT Sloan SAC 2019** [VERIFIED]
  - A deep network predicts the targeted receiver. It identified the target in 60% of cross-validated cases, and passes to the predicted receiver were completed 74% of the time versus 55% otherwise.
  - Source: [Sloan page](https://www.sloansportsconference.com/research-papers/deepqb-deep-learning-with-player-tracking-to-quantify-quarterback-decision-making-performance)
  - *Single-rookie computability:* low, because it is a QB decision model that needs all receivers.
- **Yurko, Ventura & Horowitz (2019), "nflWAR: A Reproducible Method for Offensive Player Evaluation in Football," JQAS 15(3):163–183; arXiv:1802.00998** [VERIFIED]
  - Play-by-play expected points via multinomial logistic regression, then WPA/EPA-based wins above replacement. It does not use tracking data.
  - Sources: [alphaxiv abs](https://alphaxiv.org/abs/1802.00998); [De Gruyter DOI 10.1515/jqas-2018-0010](https://www.degruyterbrill.com/document/doi/10.1515/jqas-2018-0010/html)
  - *Relevance:* a framework for converting play outcomes to value. It could weight rookie plays by EPA if play-by-play data is joined in.
- **Nguyen, Yurko & Matthews, "Here Comes the STRAIN: Analyzing Defensive Pass Rush in American Football with Player Tracking Data," arXiv:2305.10262 (2023); published in The American Statistician 78(2):199–208 (2024)** [VERIFIED; the year differs by source, 2023 online versus 2024 print]
  - STRAIN borrows strain rate from materials science. It combines the rusher-to-QB distance with the rate at which that distance shrinks, roughly the closing velocity divided by the distance, computed frame by frame. A multilevel model estimates each rusher's contribution. Data: weeks 1–8 of the 2021 season.
  - Sources: [arXiv](https://arxiv.org/pdf/2305.10262); [Loyola eCommons](https://ecommons.luc.edu/math_facpubs/47)
  - *Single-rookie computability:* **medium**. The QB is not tracked. A proxy is a STRAIN-like rate toward a fixed pocket point, for example the snap spot 7 yards behind the line of scrimmage, using only the rookie EDGE/DT track. Validate it against NGS `time_to_pressure` and `pressure_allowed`.
- **Nguyen, Jiang, Ellingwood & Yurko, "Fractional Tackles: Leveraging Player Tracking Data for Within-Play Tackling Evaluation in American Football," arXiv:2403.14769** [VERIFIED as arXiv; a Scientific Reports venue is listed on [Yurko CV](https://stat.cmu.edu/~ryurko/static/cv.pdf)]
  - A momentum-based fractional tackle metric. A version was a BDB 2024 finalist.
  - Source: [arXiv](https://arxiv.org/pdf/2403.14769)
  - *Single-rookie computability:* partial. A defender's momentum (mass × speed) and its direction toward the ball can be computed, but the ball-carrier location is unknown.
- **"A Bayesian circular mixed-effects model for explaining variability in directional movement in American football," arXiv:2507.06122 (2025)** [VERIFIED title; authors not captured in search snippet]
  - Models the variability of movement direction, a circular outcome. This links directly to turning and change-of-direction (COD) capacity. The authors are likely the Nguyen/Yurko group, but that is unconfirmed.
  - Source: [arXiv](https://arxiv.org/pdf/2507.06122)
- **Next Gen Stats definitions** (secondary sources; no official glossary page was retrieved):
  - *Get Off*: how quickly a defender gets past the line of scrimmage after the snap, on average. It is highly stable year to year. Sources: [STRAIN paper](https://arxiv.org/pdf/2305.10262v1); [FiveThirtyEight](https://fivethirtyeight.com/features/the-nfl-has-a-new-way-to-measure-the-explosiveness-of-pass-rushers)
  - *Time to pressure*: reported as a player average. For example, Jeffery Simmons averaged 2.48 s, the fastest among 34 players with ≥25 pressures. Source: [NFL.com](https://www.nfl.com/news/11-outrageous-next-gen-stats-entering-week-12)
  - *Tight window*: less than 1 yard of separation when the pass arrives. Source: [NFL.com](https://www.nfl.com/news/11-outrageous-next-gen-stats-entering-week-12)
  - *Pressure probability*: an NGS article exists. Source: [NFL.com](https://www.nfl.com/news/next-gen-stats-introduction-to-pressure-probability)
  - *Expected Rushing Yards*: derived from the BDB 2020 winner. Source: [NFL.com](https://www.nfl.com/news/next-gen-stats-intro-to-expected-rushing-yards)

### Inferences
- **Feature recipes that can be computed from one player's 10 Hz track (x, y, s, a, o, dir):**
  1. **In-game speed envelope:** per-player max speed and its 95th/99th percentile across plays. Filter out speeds above roughly 12 yd/s as glitches. Time to 90% of max speed from the snap.
  2. **Acceleration and deceleration envelope:** the high percentiles of positive and negative `a`. Note that `a` in NGS data is the magnitude, so derive a signed tangential acceleration from the derivative of `s`.
  3. **Turning and curvature capacity:** heading-change rate (unwrap `dir`, take its derivative) and curvature κ = |dθ/ds|. Plot the "speed–curvature frontier": the maximum speed reached at each curvature bin, or equivalently the maximum centripetal acceleration v²κ.
  4. **Break sharpness for WR/TE/DB:** the speed drop into the break, the time spent below a threshold speed, the angle change, and the re-acceleration over the 0.5 s after the break. Condition on the route cluster (Chu et al.).
  5. **Get-off and burst for DL/EDGE:** displacement toward the backfield and speed 0.5 s and 1.0 s after the snap. Validate against NGS `player_get_off`.
  6. **STRAIN-like closing rate:** the closing velocity toward a fixed pocket point divided by the distance to it. Relate it to `time_to_pressure` and `pressure_allowed`.
  7. **Body-orientation versus movement mismatch:** |o − dir|, for example backpedal and hip-flip timing in DBs, or pass-set kick-slide in OL.
- Outcome links can use the NGS play-level stats as responses, for example mixed models with a random player effect (as in STRAIN) and the movement features as covariates.

### Gaps
- I could not open the full texts, because arXiv was blocked in this sandbox. Exact model formulas and performance numbers for Going Deep, EHCP and STRAIN are not recorded here beyond the abstracts.
- **[UNVERIFIED]** I could not find a specific paper by "Sumer" on separation. No source located it, so do not cite it.
- I did not retrieve an official Next Gen Stats glossary for separation_at_pass_forward, player_get_off, time_to_pressure or pressure_allowed. The 2027 Kaggle data page returned no content.

## Soccer movement models: pitch control, reachable regions, ghosting

### Takeaway
Soccer's key idea is a per-player **motion model**: given position, velocity and physical limits, where can the player reach in time t? It underlies Fernandez & Bornn's influence model, Spearman's time-to-intercept pitch control, and Brefeld et al.'s probabilistic movement models. Empirical reachable regions are fitted from each player's own trajectories, so this transfers well to a single rookie's track. It works as an "athlete fingerprint" of how far he can get in 0.5 s or 1 s from each speed and heading state.

### Cited Findings
- **Fernández & Bornn (2018), "Wide Open Spaces: A statistical technique for measuring space creation in professional soccer," MIT Sloan SAC 2018** [VERIFIED listing; a mirrored PDF is labeled 2017/2018]
  - A continuous pitch-control surface. Each player's influence is a bivariate Gaussian whose covariance is shaped by the player's velocity vector and distance to the ball.
  - Sources: [Sloan page](https://sloansportsconference.com/research-papers/wide-open-spaces-a-statistical-technique-for-measuring-space-creation-in-professional-soccer); description in [Martens, Dick & Brefeld 2021, Frontiers](https://www.frontiersin.org/articles/10.3389/fspor.2021.676179/text)
- **Spearman (2018), "Beyond Expected Goals," MIT Sloan SAC 2018** [PARTIALLY VERIFIED: title, author and year are cited widely; venue not confirmed in retrieved pages]
  - Off-ball scoring opportunity: pitch control × probability of scoring at each location. A physics-based model of time to intercept.
  - Sources: [Training Ground Guru interview](https://archive.trainingground.guru/articles/william-spearman-how-liverpool-create-pitch-control); [Analytics FC blog](https://analyticsfc.co.uk/blog/2018/07/23/in-the-press-messis-walking-for-fivethirtyeight/); [Spearman bio](https://projectproduction.org/bios/william-spearman/)
- **Brefeld, Lasek & Mair (2019), "Probabilistic Movement Models and Zones of Control," Machine Learning 108, doi:10.1007/s10994-018-5725-1** [VERIFIED]
  - Estimates **individual** movement models from positional data: a distribution of displacement over a time lag, conditioned on the current velocity, which is binned into stand, walk, jog, run and sprint. These are then turned into zones of control. The method scales and can be computed in a distributed way.
  - Sources: [mlanthology](https://mlanthology.org/mlj/2019/brefeld2019mlj-probabilistic); [author PDF](https://ml3.leuphana.de/publications/mlj-soccer2018.pdf); description of the 1 s window and speed bins in [PMC8440569](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8440569/)
- **Martens, Dick & Brefeld (2021), "Space and Control in Soccer," Frontiers in Sports and Active Living** [VERIFIED]
  - Replaces the coarse Gaussian influence of Fernández & Bornn with data-driven movement models for each player.
  - Sources: [Frontiers](https://www.frontiersin.org/articles/10.3389/fspor.2021.676179/text); [Leuphana](https://fis.leuphana.de/en/publications/space-and-control-in-soccer/)
- **"A Validation Procedure for the Estimation of Reachable Regions in Football"** (University of Vienna eprint 7324) [VERIFIED title; authors and year not captured]
  - Most motion models have not been validated on real data. Constant-speed or constant-acceleration models without a speed cap are particularly inappropriate for separating reachable from unreachable locations.
  - Source: [univie eprint](https://eprints.cs.univie.ac.at/7324)
- **Le, Carr, Yue & Lucey (2017), "Data-Driven Ghosting using Deep Imitation Learning"** [PARTIALLY VERIFIED: title and authors appear in a curated reading list; the Sloan SAC 2017 venue is not confirmed by a retrieved page]
  - Learns "ghost" defenders, meaning league-average expected positions, and compares actual players with them.
  - Source: [nbviewer reading list](https://nbviewer.org/github/eddwebster/football_analytics/tree/master/research/papers)

### Inferences
- **Rookie "reachable-region fingerprint":** for each rookie, bin the frames by (speed bin, heading). For each bin, collect the displacement vectors over Δt = 0.5 s and 1.0 s, expressed in the player's velocity frame. Summarize them as quantile contours, for example the area of the 95% hull or the maximum lateral displacement at a given forward speed.
  - This is the Brefeld-style model applied to one player, so it needs no other players.
  - Comparing it across rookies of the same position gives an "agility envelope". Comparing it with Combine drills tests transfer.
- Pitch control and ghosting themselves need all 22 players, so they are not computable with 2027 data. Their kinematic sub-models can still be computed.

### Gaps
- I did not confirm Spearman's 2018 venue or the venue for Le et al. from primary pages.

## Movement-profile and athlete-fingerprint ideas

### Takeaway
No peer-reviewed football paper retrieved here defines an in-game "movement signature" per player. The closest evidence is:
- STRAIN and Fractional Tackles, which are rate-based kinematics;
- Brefeld's individual motion models;
- the circular-direction model (arXiv:2507.06122);
- public 2027 BDB entries that build Combine-to-game speed, burst, braking and COD features.

### Cited Findings
- The 2027 BDB (Kaggle) reportedly provides:
  - NGS prospect scores combining athleticism and college production, for 510 rookie prospects;
  - Combine sensor tracking every 0.1 s;
  - rules that suggest measuring change of direction, deceleration into breaks, and acceleration out of cuts.

  These details come from a search-result summary only, because the page did not render. Sources: [Kaggle BDB 2027 data](https://www.kaggle.com/competitions/nfl-big-data-bowl-2027/data); [i-programmer news](https://www.i-programmer.info/news/204-challenges/19221-nfl-big-data-bowl-2027-competition-now-open.html)
- Public 2027 work in progress (not peer-reviewed):
  - "Measure the Athlete, Not the Drill": compares top speed, burst, braking and bending in Combine reps versus NFL snaps. It reports that in-game COD is stable (split-half 0.63–0.95) but Combine COD is not, and that 0 of 144 position-drill → NFL tests survive a family-wise permutation test. Source: [GitHub bansal1600](https://github.com/bansal1600/kaggle-NFL-big-data-2027)
  - Other public repos are scaffolds with no results yet. Sources: [maxquirk](https://github.com/maxquirk/big-data-bowl); [Hclark36](https://github.com/Hclark36/2027-NFL-Big-Data-Bowl) (acceleration timing and shape beyond the 40-yard time); [jamescush003-code](https://github.com/jamescush003-code/NFL-Big-Data-Bowl-2026-27)
- A 2022 BDB grand finalist reportedly found that a ball carrier's "effective acceleration" was the most important input for estimating yards gained. This is from a search-result summary only; I did not identify the entry. Source: [Kaggle BDB 2022 discussion](https://www.kaggle.com/c/nfl-big-data-bowl-2022/discussion/277786)

### Inferences
- Candidate fingerprint vector per rookie:
  - speed: max and p95 speed;
  - acceleration: time to p90 speed, peak signed acceleration and deceleration, and an acceleration–speed profile (the intercept and slope of max acceleration against current speed, as in the sprint-profiling "A–S profile" literature) [concept from sprint science; no source retrieved here];
  - turning: the speed–curvature frontier, plus the reachable-region area at 0.5 s and 1 s;
  - break timing: the deceleration-to-reacceleration interval at breaks, and the get-off displacement.
- Use split-half reliability across plays, as the bansal1600 entry did, to show that a feature measures a trait before relating it to outcomes.

### Gaps
- No verified peer-reviewed paper on NFL in-game acceleration–speed profiles was retrieved.
- The full official 2027 data schema could not be read, so the exact column names are taken from the assignment brief, not a source.

## Prior NFL Big Data Bowl winners and finalists (2019–2026)

### Takeaway
Winning BDB entries usually:
1. define a frame-level probability or value from tracking data, such as expected yards, tackle probability, pressure or ghost defenders;
2. aggregate it into a player metric;
3. visualize it.

Few winners measured pure athleticism. The nearest are the effective-acceleration finding (2022), STRAIN and Get Off, and momentum-based fractional tackles (2024).

### Cited Findings
- **2019 (passing plays; inaugural):**
  - College winner: Chu, Reyers, Thomson & Wu (SFU), route identification. Sources: [SFU News](https://www.sfu.ca/sfunews/stories/2019/04/statistics-students-impress-the-nfl-with-their-moves.html); [NFL Ops Q&A](https://operations.nfl.com/stats-central/stats-articles/qa-with-2019-big-data-bowl-college-winners)
  - CMU finalists Brendon Gu & Peter Wu proposed a pass-interference rule change. Source: [CMU](https://www.cmu.edu/news/stories/archives/2019/february/big-data-bowl.html)
  - Overall recaps: [NFL Ops past recaps](https://operations.nfl.com/the-game/big-data-bowl/2019-big-data-bowl)
- **2020 (expected rushing yards, Kaggle prediction):**
  - Winner "The Zoo", Philipp Singer & Dmitry Gordeev. A 2D CNN on the relative location, speed and acceleration of every player at the handoff. It won by a large margin and became the basis for NGS Expected Rushing Yards.
  - Sources: [NFL Ops 2020 results](https://operations.nfl.com/updates/the-game/2020-big-data-bowl-results); [NFL Ops recap](https://operations.nfl.com/stats-central/stats-articles/2020-big-data-bowl-recap); [NFL.com xRushYds](https://www.nfl.com/news/next-gen-stats-intro-to-expected-rushing-yards)
- **2021 (pass coverage, 2018 data):**
  - College winners: Ella Summer (UVA) and Jill Reiner (Denison).
  - Open winners:
    - Toumi, Furman, Robinson & ElHabr;
    - Venzor & Gartenhaus;
    - Joe Andruzzi;
    - Subbaiah, Chu, Reyers & Wu;
    - Peng, Richards, Walczak & Werner.
  - Entry titles were not captured. Sources: [Kaggle 2023 discussion listing past winners](https://www.kaggle.com/competitions/nfl-big-data-bowl-2023/discussion/361175); [NFL video Peng et al.](https://www.nfl.com/videos/2021-big-data-bowl-wei-peng-marc-richards-sam-walczak-jack-werner); [NFL video Summer](https://www.nfl.com/videos/2021-big-data-bowl-ella-summer); [Denison](https://denison.edu/academics/data-analytics/feature/141466)
- **2022 (special teams):**
  - Winner Robyn Ritchie, Brendan Kumagai, Ryker Moreau & Elijah Cavan, "Punt Returns: Using the Math to Find the Path". There were 8 finalists from more than 200 submissions. Source: [NFL.com winners video](https://www.nfl.com/videos/2022-big-data-bowl-winners-announcement)
  - A Penn graduate student was a finalist. Source: [Daily Pennsylvanian](https://www.thedp.com/article/2022/03/penn-grad-student-finalists-nfl-data-bowl-competion)
- **2023 (linemen, pass rush and protection):**
  - Winner from the University of Toronto: Hassaan Inayatali, Aaron White & Daniel Hocevar. A pressure model rendered as animated heat maps; exact title not captured. Source: [All Access Football](https://www.allaccessfootball.com/p/champions-have-been-crowned-for-the)
  - STRAIN (Nguyen, Yurko, Matthews) came from this data and theme. Source: [Substack](https://statthinksportsanalytics.substack.com/p/here-comes-the-strain-and-cmsac)
- **2024 (tackling):**
  - Winner: Matthew Chang, Katherine Dai, Daniel Jiang & Harvey Cheng, "Uncovering Missed Tackle Opportunities". A defender is charged with a missed tackle when his tackle probability exceeds 75% for at least 0.5 s, then drops, and no tackle follows within 1 s. Sources: [Knowable Magazine](https://knowablemagazine.org/content/article/technology/2024/how-next-gen-data-analytics-changing-american-football); [Matt Chang podcast](https://podcasts.apple.com/us/podcast/matt-chang-nfl-big-data-bowl-winner/id1477998252?i=1000649003450)
  - Finalists included Nguyen, Jiang, Ellingwood & Yurko, "Momentum-based fractional tackles", and Ben Davis & Nidiyan Rajendran, "Pull the Plug". There were five finalists. Sources: [NFL.com finalists](https://www.nfl.com/news/nfl-announces-finalists-for-sixth-annual-big-data-bowl); [CMU](https://www.cmu.edu/dietrich/statistics-datascience/news/2024/nfl-big-data-bowl.html)
- **2025 (pre-snap):**
  - There were five finalists, announced Feb 18, 2025, each receiving $12,500, out of more than 400 participants. Source: [NFL media release](https://media.nfl.com/news-and-releases/corporate-communications/national-football-league-announces-finalists-in-seventh-annual-b)
  - Finalist topics included predicting defensive schemes from alignment, predicting whether a tight end blocks, and scoring coverage disguise. Source: [Sportico](https://www.sportico.com/leagues/football/2025/super-bowl-2025-predictions-chiefs-eagles-offensive-scheme-motion-data-1234826674/)
  - An NYU duo is reported as the winner, but the names and title were not retrieved because the page fetch failed. Source: [NYU SPS](https://www.sps.nyu.edu/about/news-and-ideas/articles/preston-robert-tisch-institute-for-global-sport/2025/nyu-duo-crowned-winners-of-the-2025-nfl-big-data-bowl.html)
- **2026 (ball in the air):**
  - Winner Lucca Ferraz (Rice), "Ghostbusters". It evaluates defender movement while the ball is in the air against hypothetical distributions of ghost defenders. Source: [NFL Ops BDB page](https://operations.nfl.com/programs-initiatives/innovation/big-data-bowl)
  - Finalist from UW–Madison, "Path Against the Pass": transformers on how defenders close space after the throw. Source: [UW Stats](https://stat.wisc.edu/2026/03/09/statistics-affiliated-team-presents-innovative-sports-data-project-at-nfl-combine/)
  - A BYU team was among five winners, analyzing defender actions between release and catch; the year is unclear. Source: [BYU](https://science.byu.edu/byu-student-finalists-tackle-the-nfl-big-data-bowl-present-to-league-executives)
  - Kaggle page: [BDB 2026 Analytics](https://www.kaggle.com/competitions/nfl-big-data-bowl-2026-analytics)
- **2027 (ninth annual; rookies and Combine):** announced in October 2026. Sources: [SVG announcement](https://www.sportsvideo.org/2026/10/08/nfl-announces-ninth-annual-big-data-bowl-powered-by-aws/); [Kaggle 2027](https://www.kaggle.com/competitions/nfl-big-data-bowl-2027/data)

### Inferences
- Patterns worth reusing for the rookie theme:
  - a threshold- or episode-based event definition (2024's 75%/0.5 s rule), for example a "burst episode" or a "sharp break" event;
  - a ghost or expected baseline (2026), here a position-average rookie motion model as the ghost against which each rookie's acceleration and turning is compared;
  - a multilevel model with player random effects (STRAIN, fractional tackles) to shrink noisy per-player estimates.

### Gaps
- Exact entry titles and links for most 2021, 2023 and 2025 winners, and for the full 2026 finalist list, could not be retrieved because operations.nfl.com was unreachable from the sandbox.
- The 2025 winner's names and title are unconfirmed.
- The 2022 "effective acceleration" finalist is unidentified.
