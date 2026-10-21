# Statistical Methods for Linking Pre-Draft Athletic Tests to NFL Performance (small n, many positions, noisy opportunity-dependent outcomes)

Verification note: Crossref API and arxiv.org were unreachable from this sandbox (proxy 403 / DNS failure). References were checked by web search against publisher, PubMed Central, RePEc/IDEAS, Project Euclid, JSS and journal-society records. Each entry is tagged:
- **[V]** = bibliographic details (authors, year, title, venue, DOI) confirmed by at least one publisher, indexing or repository record found in this session.
- **[V-partial]** = existence confirmed, but some detail (pages, DOI) taken from a secondary aggregator only.
- **[UNVERIFIED]** = standard reference from background knowledge, not checked in this session. Confirm it before citing.

No effect sizes or numbers are invented. Where a number appears, it comes from the cited abstract or record.

---

## Q1. Empirical Bayes / hierarchical shrinkage and metric reliability ("stabilization")

### Takeaway
With about 500 players and outcomes that depend on snaps or targets, raw per-player rates are too noisy to use directly. Shrink them toward position-level means using empirical Bayes or a hierarchical model. Then judge every candidate metric (combine-derived or outcome) by its reliability, i.e. its signal-to-noise ratio, before correlating it with anything. Franks et al. (2016) give a formal "meta-metric" framework for this: discrimination, stability and independence.

### Cited Findings
- **Efron, B. & Morris, C. (1975). "Data analysis using Stein's estimator and its generalizations." *JASA* 70(350): 311–319. DOI 10.1080/01621459.1975.10479864 [V].** The paper reviews the James–Stein estimator in an empirical Bayes setting. It applies the estimator to baseball batting averages, toxoplasmosis prevalence rates and the exact size of Pearson's chi-square test. The authors report that in each example the mean squared error of these rules is under half that of the sample mean. — [McGill-hosted PDF](https://www.medicine.mcgill.ca/epidemiology/hanley/bios602/MultilevelData/EfronMorrisJASA1975.pdf); [JSTOR 2285814 record via search]
- **Morris, C. N. (1983). "Parametric empirical Bayes inference: theory and applications." *JASA* 78(381): 47–55. DOI 10.1080/01621459.1983.10477920 [V-partial; DOI from an aggregator, JSTOR stable 2287098].** This is the standard reference for parametric empirical Bayes, including interval estimation. — [errorstatistics.com copy](https://errorstatistics.com/wp-content/uploads/2015/11/morris.pdf); [Duke record of discussion](https://scholars.duke.edu/publication/653341)
- **Brown, L. D. (2008). "In-season prediction of batting averages: A field test of empirical Bayes and Bayes methodologies." *Annals of Applied Statistics* 2(1): 113–152. DOI 10.1214/07-AOAS138 [V].**
  - Design: estimate each batter's latent ability from early-season 2005 MLB data (e.g., the first 3 months), then predict the rest of the season.
  - Finding: a new nonparametric EB procedure performed best on the full data. Familiar EB/Bayes methods did better on more homogeneous subsets. The naive raw-average predictor performed worst in every case.
  - Method: a variance-stabilizing transformation turns binomial counts into approximately normal values with known variance. The paper also builds an empirical test of the binomial model assumption.
  - Sources: [arXiv 0803.3697](https://arxiv.org/pdf/0803.3697); [DOI](https://doi.org/10.1214/07-aoas138)
- **Franks, A. M., D'Amour, A., Cervone, D. & Bornn, L. (2016). "Meta-analytics: tools for understanding the statistical properties of sports metrics." *JQAS* 12(4): 151–165. DOI 10.1515/jqas-2016-0098 [V].**
  - Author list: Miller and Goldsberry are acknowledged, not authors. The task prompt's attribution should read Franks, D'Amour, Cervone & Bornn.
  - Three "meta-metrics": **stability** over time, **discrimination** between players, and **independence**, meaning whether a metric adds new information beyond existing ones. The paper demonstrates them on NBA and NHL metrics.
  - Open preprint: arXiv 1609.09830.
  - Sources: [RePEc/IDEAS](https://ideas.repec.org/a/bpj/jqsprt/v12y2016i4p151-165n3.html); [arXiv PDF](https://www.arxiv.org/pdf/1609.09830)
- **[UNVERIFIED]** Efron, B. (2010). *Large-Scale Inference: Empirical Bayes Methods for Estimation, Testing, and Prediction*. Cambridge University Press. This is a useful textbook bridge between EB shrinkage and FDR, but it was not checked in this session.

### Inferences
- **Why EB fits this problem.** Outcomes such as yards per route, PFF-style grades and pressure rate are ratios with very unequal denominators (snaps). EB or hierarchical shrinkage weights each player's rate by its precision:
  - posterior mean = w·raw + (1−w)·prior mean, with w = τ²/(τ² + σ²/n_i)
  - This prevents low-snap players from dominating the correlations at the extremes.
  - Use a position-specific prior, or a hierarchical prior with position nested in position group.
  - For counts, use beta-binomial or Poisson-gamma models. Alternatively, use Brown's variance-stabilizing transform followed by a normal-normal EB model.
- **Stabilization / reliability.**
  - Estimate the reliability of each outcome as a function of opportunity. Options include split-half correlations (odd vs even games or snaps, with the Spearman–Brown step-up) or the variance-components ratio τ²/(τ² + σ²/n).
  - Report the n at which reliability reaches about 0.5 or 0.7.
  - Franks et al.'s "stability" meta-metric formalizes the same idea. Its "discrimination" meta-metric gives the between-player signal fraction within a season.
- **Pitfall: unreliable outcomes cap the correlation.** The ceiling is roughly √(rel_X·rel_Y), so a low-reliability outcome caps any combine-to-NFL correlation regardless of the combine metric's true value. Always report reliabilities next to validity coefficients.
- **Pitfall: the EB prior must not use the predictor.** If the prior mean depends on the combine metric, shrinkage pulls players toward the predicted value and inflates the correlation. Either shrink to a position mean only, or fit the predictor and the shrinkage jointly in one hierarchical model.
- **Pitfall: shrinkage bias at the extremes.** Shrunk estimates are biased toward the mean for true outliers, which are often the elite athletes of interest. Use full posteriors rather than point estimates in the second-stage regression, or fit one joint model.

### Gaps
- I could not retrieve the full text of Franks et al. (arXiv was unreachable), so I cannot quote the exact estimator formulas for the discrimination, stability and independence meta-metrics.
- I found no peer-reviewed paper that publishes stabilization points for NFL outcome metrics. The sabermetric "stabilization point" work (e.g., by baseball analysts) is mostly in blogs and was not verified here.

---

## Q2. Measurement error and regression dilution (attenuation correction)

### Takeaway
Combine and tracking tests have test-retest error, and NFL outcomes are noisy. Both effects attenuate correlations and slopes toward zero. Error in a covariate (for example, 40 time used as a control) also leaves "residual confounding," which makes a new metric look incrementally valid when it is not. Correct for this with reliability-based disattenuation, regression calibration or SIMEX, or latent-variable/SEM models. Propagate the uncertainty of the reliability estimate as well.

### Cited Findings
- **Spearman, C. (1904). "The proof and measurement of association between two things." *American Journal of Psychology* 15(1): 72–101. JSTOR 1412159 [V-partial; via secondary sources and a full-text reprint].**
  - Origin of the correction for attenuation: r_true = r_obs / √(rel_X·rel_Y).
  - The correction can produce values above 1.00 and assumes equal error variances.
  - Sources: [gwern reprint](https://www.gwern.net/doc/psychology/1904-spearman.pdf); [Wikipedia mirror on correction for attenuation](https://static.hlt.bme.hu/semantics/external/pages/pszichometriai_g-faktor/en.wikipedia.org/wiki/Correction_for_attenuation.html); [UvA PDF on limitations](https://pure.uva.nl/ws/files/2208249/153516_09.pdf)
- **Frost, C. & Thompson, S. G. (2000), not 2004. "Correcting for regression dilution bias: comparison of methods for a single predictor variable." *JRSS Series A* 163(2): 173–189. DOI 10.1111/1467-985X.00164 [V].**
  - The year is 2000, not 2004 as given in the task prompt.
  - The paper compares six methods for estimating the correction factor, grouped into regression-based and correlation-based approaches.
  - It gives formulas showing that imprecision in the estimated correction factor matters when the factor is large and the repeat-measurement subset is small. That is exactly the case when only a subset of players has repeated tests.
  - Sources: [IDEAS/RePEc](https://ideas.repec.org/a/bla/jorssa/v163y2000i2p173-189.html); [Wikipedia: Regression dilution](https://en.wikipedia.org/wiki/Regression_dilution)
- Longford (2001) replied to Frost & Thompson by pointing to errors-in-variables models as an alternative. Frost & White (2005, *Int. J. Epidemiology*) examined whether simple corrections overcorrect when risk factors change over time. — [Wikipedia: Regression dilution](https://en.wikipedia.org/wiki/Regression_dilution) (secondary; primary records not checked)
- A tutorial on correction methods and sample-size calculation for regression dilution is available open access. — [PMC3410287](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3410287/) (bibliographic details not extracted)
- **Carroll, R. J., Ruppert, D., Stefanski, L. A. & Crainiceanu, C. M. (2006). *Measurement Error in Nonlinear Models: A Modern Perspective*, 2nd ed. Chapman & Hall/CRC, Monographs on Statistics and Applied Probability 105. ISBN 9781584886334 [V].** This is the standard reference for regression calibration and SIMEX. Both appear as named sections in its table of contents. — [Routledge](https://www.routledge.com/Measurement-Error-in-Nonlinear-Models-A-Modern-Perspective/Carroll-Ruppert-Stefanski-Crainiceanu/p/book/9781584886334); [Author page](https://carroll.stat.tamu.edu/eiv-secondedition/)
- **Westfall, J. & Yarkoni, T. (2016). "Statistically controlling for confounding constructs is harder than you think." *PLoS ONE* 11(3): e0152719. DOI 10.1371/journal.pone.0152719 [V].**
  - Common multiple-regression strategies for showing incremental validity have extremely high Type I error rates when covariates are measured with error.
  - The error rates peak with large samples and moderate reliability, approaching 100% in some cases.
  - The authors recommend SEM with multiple indicators.
  - Sources: [PMC4816570](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4816570/)
- **[UNVERIFIED]** Fuller, W. A. (1987). *Measurement Error Models*. Wiley. A classic text on errors-in-variables regression; not checked here.

### Inferences
- **Where to get reliabilities for combine data.** Many combine events record two attempts (40, vertical, broad). Use the intraclass correlation (ICC) between attempts as the reliability estimate. For tracking-derived speed metrics, use reliability across reps or across segments.
  - Caveat: within-day ICC overstates the reliability of the "true trait," because day-level factors (track, timing system, pro day vs combine) are shared across attempts. Model test site and timing method as a separate error or bias component.
- **Westfall & Yarkoni applied to this problem.** Asking whether a new tracking speed metric predicts beyond the 40 time is exactly the case they warn about. The 40 time is an error-laden proxy for "true speed," so the new metric will absorb leftover speed signal and look incrementally valid. Mitigations:
  - (a) Model a latent speed factor from several indicators (40, splits, 20-yd shuttle, tracking max speed) with SEM.
  - (b) Use regression calibration or SIMEX on the covariate with an externally estimated reliability.
  - (c) Run a sensitivity analysis over a plausible reliability range.
- **Report both versions.** Give observed and disattenuated estimates. Bootstrap the disattenuated estimate jointly with the reliability estimates, as Frost & Thompson's point about correction-factor imprecision implies. Never report disattenuated r > 1 without flagging it.

### Gaps
- I found no published test-retest reliability values for NFL combine events in this session, so none are reported. They need to be estimated from the data itself (e.g., attempt 1 vs attempt 2).

---

## Q3. Functional data analysis (FDA) for speed curves and comparing curves

### Takeaway
Tracking gives a velocity–time or velocity–distance curve per rep. FDA can treat the whole curve as the predictor rather than reducing it to a 40 time:
- smooth the curves with B-splines
- register (align) them
- summarize them with functional PCA
- regress outcomes on the FPC scores (scalar-on-function regression)

An alternative is the parametric mono-exponential sprint model (Samozino/Morin), which gives interpretable max-speed (v_max) and acceleration-constant (τ) parameters. With n≈500 split across positions, a few FPC scores or two or three parametric parameters per player are the right level of complexity.

### Cited Findings
- **Ramsay, J. O. & Silverman, B. W. (2005). *Functional Data Analysis*, 2nd ed. Springer Series in Statistics. DOI 10.1007/b98888; ISBN 978-0-387-40080-8 [V].** This is the core textbook for smoothing, registration, functional PCA and functional linear models. — [Springer](https://link.springer.com/book/10.1007/b98888)
- **Wang, J.-L., Chiou, J.-M. & Müller, H.-G. (2016). "Functional data analysis." *Annual Review of Statistics and Its Application* 3: 257–295. DOI 10.1146/annurev-statistics-041715-033624 [V].** A review of FPCA, functional regression and registration. — [arXiv 1507.05135](https://arxiv.org/pdf/1507.05135)
- **Srivastava, A., Klassen, E., Joshi, S. H. & Jermyn, I. H. (2011). "Shape analysis of elastic curves in Euclidean spaces." *IEEE TPAMI* 33(7): 1415–1428. DOI 10.1109/TPAMI.2010.184 [V].**
  - Introduces the square-root velocity (SRV) representation. Under it, the elastic metric becomes L2 and reparameterization acts by isometries.
  - This is the basis for elastic (phase–amplitude) registration of curves.
  - Sources: [Durham repository](https://durham-repository.worktribe.com/output/1537659)
- An arXiv tutorial, "Functional Data Analysis: An Introduction and Recent Developments" (arXiv 2312.05523), uses running biomechanics as its examples. It argues that reducing curves to scalar summaries can inflate error rates, and that FDA can locate *where/when* along the movement differences occur. — [arXiv 2312.05523](https://arxiv.org/pdf/2312.05523) (author list not extracted; peer-reviewed venue not confirmed)
- **Samozino, P., Rabita, G., Dorel, S., Slawinski, J., Peyrot, N., Saez de Villarreal, E. & Morin, J.-B. (2016). "A simple method for measuring power, force, velocity properties, and mechanical effectiveness in sprint running." *Scandinavian Journal of Medicine & Science in Sports* 26(6): 648–658. DOI 10.1111/sms.12490 [V; online 2015].**
  - A field method that fits sprint data to estimate force-velocity and power-velocity profiles, validated against force plates.
  - The search snippet reports nine sprinters and between-trial SEM below 5%.
  - Sources: [HAL](https://hal.univ-reunion.fr/hal-01389134)
- The R package **{shorts}** implements mono-exponential sprint modelling (maximal sprinting speed, maximal acceleration and related metrics) for timing-gate or radar data. — [CRAN README](https://cran.r-project.org/web/packages/shorts/readme/README.html)
- **[UNVERIFIED]** Ramsay, J. O., Hooker, G. & Graves, S. (2009). *Functional Data Analysis with R and MATLAB*. Springer (Use R!). Companion to the `fda` R package.
- **[UNVERIFIED]** Packages `refund` (penalized functional regression, scalar-on-function) and `fdasrvf` (SRV elastic registration) exist in R. Their exact citations were not checked.

### Inferences
- **Pipeline:**
  - (1) Put each rep on a common distance grid (0–40 yd), because distance-indexed curves avoid most timing misalignment.
  - (2) Smooth velocity with penalized B-splines.
  - (3) Optionally separate phase (when acceleration happens) from amplitude (how fast) with SRV registration. The phase component can itself be a predictor.
  - (4) Run FPCA. Keep about 2–4 components; check variance explained and interpretability (e.g., FPC1 ≈ overall speed, FPC2 ≈ early acceleration vs top speed).
  - (5) Regress outcomes on FPC scores within a mixed model (Q5), controlling for body mass.
- **Comparing curves between groups** (e.g., drafted vs undrafted, positions): use functional ANOVA or pointwise tests with simultaneous bands. Permutation-based global tests over the whole curve are one option.
- **Pitfall: FPCA mixes positions.** FPCA on pooled positions mostly captures position or body-mass differences. Compute FPCs within position groups, or residualize on mass and position first.
- **Pitfall: leakage.** Choosing the number of FPCs or the smoothing penalty on the full data leaks information. Nest those choices inside cross-validation.
- **Pitfall: collinearity with the 40 time.** The 40 time is the integral of 1/velocity over distance, so FPC1 will be highly collinear with it. Incremental-validity tests (Q4) must account for that, preferably with the latent-variable approach from Q2.

### Gaps
- I found no peer-reviewed study applying FDA to NFL combine or tracking sprint curves. The search for "functional data analysis sprint velocity curves athletes" returned only general FDA and parametric sprint-profiling material.

---

## Q4. Incremental validity, permutation tests, bootstrap CIs and multiple comparisons

### Takeaway
The key question is whether a new metric adds information beyond the 40 time, body mass and draft pick. Test it with nested models: partial correlation or ΔR², and out-of-sample predictive gain. Get p-values from a Freedman–Lane residual permutation and CIs from a bootstrap that resamples players. Control the false discovery rate across about 15 positions × several metrics with Benjamini–Hochberg. Draft pick is a "post-treatment" summary of scouts' information, so condition on it only when the question is *market-adjusted* added value.

### Cited Findings
- **Benjamini, Y. & Hochberg, Y. (1995). "Controlling the false discovery rate: a practical and powerful approach to multiple testing." *JRSS Series B* 57(1): 289–300. DOI 10.1111/j.2517-6161.1995.tb02031.x [V].** A sequential Bonferroni-type step-up procedure controls the FDR for independent test statistics. — [DOI record (citedrive)](https://citedrive.com/en/discovery/controlling-the-false-discovery-rate-a-practical-and-powerful-approach-to-multiple-testing); [PDF](https://www.dcscience.net/Benjamini-Hochberg-1995-FDR.pdf)
- **Freedman, D. & Lane, D. (1983). "A nonstochastic interpretation of reported significance levels." *Journal of Business & Economic Statistics* 1(4): 292–298 [V-partial; citation confirmed via multiple citing sources].**
  - Procedure: residualize the outcome on the covariates, permute the residuals, add back the fitted covariate effects, refit, and compare the coefficient of interest.
  - Anderson & Robinson (2001) found Freedman–Lane has asymptotic correlation 1 with the exact test, higher than the alternative methods.
  - Sources: [UVM notes](https://www.uvm.edu/~statdhtx/StatPages/R/RandomizationTestsWithR/permut2.pdf); [brainder.org explainer](https://brainder.org/tag/glm/)
- **Anderson, M. J. & Legendre, P. (1999). "An empirical comparison of permutation methods for tests of partial regression coefficients in a linear model." *Journal of Statistical Computation and Simulation* 62 [V-partial; volume only, findings not retrieved].**
- **Westfall & Yarkoni (2016)** (see Q2): naive incremental-validity tests have inflated Type I error when covariates are unreliable. [V]
- **Massey, C. & Thaler, R. H. (2013). "The loser's curse: decision making and market efficiency in the National Football League draft." *Management Science* 59(7): 1479–1495. DOI 10.1287/mnsc.1120.1657 [V].** Top draft picks are significantly overvalued relative to the surplus value they deliver. This is relevant if draft slot is used as a benchmark "market prior." — [IDEAS](https://ideas.repec.org/a/inm/ormnsc/v59y2013i7p1479-1495.html)
- **Wolfson, J., Addona, V. & Schmicker, R. H. (2011). "The quarterback prediction problem: forecasting the performance of college quarterbacks selected in the NFL draft." *JQAS* 7(3) [V].**
  - Earlier studies looked only at QBs who played in the NFL. The authors include all drafted QBs since 1997, with success measured as games played and Net Points.
  - They find college and combine statistics add little predictive value for QB success. Teams combine pre-draft information fairly well, and misses reflect largely unobservable random variability.
  - Sources: [UMN Experts](https://experts.umn.edu/en/publications/the-quarterback-prediction-problem-forecasting-the-performance-of/); [IDEAS WP](https://ideas.repec.org/p/aut/wpaper/202011.html)
- **Kuzmits, F. E. & Adams, A. J. (2008). "The NFL combine: does it predict performance in the National Football League?" *Journal of Strength and Conditioning Research* 22(6): 1721–1727 [V].**
  - Data: QBs, RBs and WRs drafted 1999–2004.
  - Secondary summaries report no significant relationships except 40-yard dash with RB performance.
  - Sources: [record](https://ngdc.cncb.ac.cn/openlb/publication/OLB-PM-18841077)
- **Vincent, L. M., Blissmer, B. J. & Hatfield, D. L. (2019). "National Scouting Combine scores as performance predictors in the National Football League." *Journal of Strength and Conditioning Research* 33(1): 104–111 [V; first initials not confirmed].**
  - Data: players from 2005–2010.
  - Measures and positions: 40, vertical, broad and pro-agility, studied for QB, RB, WR, DE, DT and LB.
  - Finding: significant correlations between at least one combine measure and on-field success at every position.
  - Sources: [URI Digital Commons](https://digitalcommons.uri.edu/kinesiology_facpubs/89)
- Robbins (2010, *JSCR*) is described in secondary sources as finding that draft success is not significantly correlated with combine physical tests. [V-partial; title and pages not retrieved] — [NASE summary](https://www.naseinc.com/blog/the-nfl-combine-do-test-scores-predict-success-by-naseinc/)
- **[UNVERIFIED]** Efron, B. & Tibshirani, R. J. (1993). *An Introduction to the Bootstrap*. Chapman & Hall. Standard reference for percentile and BCa intervals.
- **[UNVERIFIED]** Benjamini, Y. & Yekutieli, D. (2001). "The control of the false discovery rate in multiple testing under dependency." *Annals of Statistics* 29(4): 1165–1188. Use it when test statistics are positively or arbitrarily dependent, e.g. the same players across correlated metrics.

### Inferences
- **Hypothesis families.** Pre-register the metric × position × outcome grid. Apply BH within each family (e.g., all position-level tests for one metric), or across the whole grid with Benjamini–Yekutieli if the dependence is complex.
  - With about 33 players per position (500/15), per-position correlations have very wide CIs. Prefer partial pooling (Q5) over 15 separate tests.
- **Bootstrap.** Resample at the **player** level (cluster bootstrap if there are multiple seasons per player). Stratify by position so small positions are not lost in resamples. Use BCa or percentile intervals and report them for Δr / ΔR² rather than relying on p-values alone.
- **Permutation.** For a partial association, use Freedman–Lane rather than permuting the raw outcome, which breaks the covariate structure. Permute within position strata.
- **Out-of-sample incremental validity.** Compare cross-validated prediction error (e.g., grouped by draft year to mimic forward prediction) for base vs base+new metric. This holds up better to overfitting than in-sample ΔR².
- **Pitfall: draft pick is a collider-like / mediator variable.** It encodes scouts' views of the athletic tests. Controlling for it answers "does the metric add value *beyond what the market already priced*." That is a legitimate and stricter question, different from "is the metric related to performance." Report both. Wolfson et al. and Massey & Thaler show that draft slot is informative but imperfect.
- **Pitfall: conditioning on making the NFL** (see Q5). Wolfson et al. stress analysing all drafted players, not only those who played.

### Gaps
- I did not retrieve full texts of Kuzmits & Adams, Vincent et al. or Robbins, so their effect sizes and outcome definitions are not reported.

---

## Q5. Mixed models with position random effects; selection bias from playing time

### Takeaway
Use a hierarchical (mixed) model with position-varying intercepts and slopes for the combine metric. It partially pools the about 15 position groups instead of fitting 15 separate regressions. Weight or model the outcome by opportunity, and address the fact that outcomes are observed only for players who earn snaps (incidental truncation). A Heckman-type selection model, a two-part/hurdle model, or simply using an outcome defined for everyone (snaps, games started, roster years) handles this.

### Cited Findings
- **Bates, D., Mächler, M., Bolker, B. & Walker, S. (2015). "Fitting linear mixed-effects models using lme4." *Journal of Statistical Software* 67(1): 1–48. DOI 10.18637/jss.v067.i01 [V].** — [JSS](https://www.jstatsoft.org/v67/i01)
- **Heckman, J. J. (1979). "Sample selection bias as a specification error." *Econometrica* 47(1): 153–161/162. DOI 10.2307/1912352 [V].**
  - Page range: commonly cited as 153–161, but the Econometric Society listing (per search summary) gives 153–162. Check the page range on JSTOR 1912352 before citing.
  - The paper treats bias from nonrandomly selected samples as an omitted-variable problem and gives a simple consistent two-step estimator.
  - Sources: [Econometric Society](https://www.econometricsociety.org/publications/econometrica/1979/01/01/sample-selection-bias-specification-error); [NBER WP 172](https://www.nber.org/papers/w0172)
- Wolfson et al. (2011) argue that earlier QB studies were biased because they analysed only QBs who appeared in NFL games. They include all drafted QBs, with games played as an outcome. [V] — [UMN Experts](https://experts.umn.edu/en/publications/the-quarterback-prediction-problem-forecasting-the-performance-of/)
- **[UNVERIFIED]** Gelman, A. & Hill, J. (2007). *Data Analysis Using Regression and Multilevel/Hierarchical Models*. Cambridge University Press. Standard reference for varying-slope models and partial pooling.
- **[UNVERIFIED]** Brms / Stan (Bürkner 2017, *JSS* 80(1)) for Bayesian hierarchical models with beta-binomial or hurdle likelihoods.

### Inferences
- **Model template (Bayesian or lme4):**
  - y_i ~ (position-specific likelihood), with η_i = α_pos[i] + β_pos[i]·metric_i + γ·mass_i (+ δ·log draft pick) + draft-year effects
  - (α_pos, β_pos) ~ MVN with position-group-level means, e.g. skill / OL / DL / LB / DB.
  - This yields a shrunk, position-specific validity slope with honest uncertainty.
  - For rate outcomes, use a binomial or Poisson likelihood with snaps or routes as exposure (offset). This is equivalent to the EB shrinkage in Q1, done jointly.
- **Opportunity selection.** Playing time is itself caused by perceived ability and draft capital, and it determines whether an efficiency outcome is observed. Options:
  - (a) Use **opportunity outcomes** that are defined for every draftee (snap share in years 1–3, games started, second contract) as primary endpoints.
  - (b) Use a **two-part / hurdle model**: P(reaches X snaps) and then efficiency given that.
  - (c) Use a **Heckman selection model**. Its identification needs an exclusion restriction, i.e. a variable that shifts playing time but not per-snap efficiency (e.g., depth-chart competition at the team or position, or draft-team roster needs). Without one, identification rests only on normality and is fragile.
  - (d) Use **inverse-probability weighting** for being observed.
  - Report the sensitivity of conclusions across these choices.
- **Pitfall: collider bias.** Restricting to players with at least N snaps is conditioning on a collider when both athleticism and unmeasured skill raise snaps. It can induce a spurious negative athleticism–efficiency association among survivors.
- **Pitfall: too few groups for random effects.** With about 15 positions, variance components are estimable but imprecise. Use weakly-informative priors (Bayesian) or group positions into about 5 position groups for the random slopes.

### Gaps
- I found no peer-reviewed NFL combine paper that explicitly fits a Heckman or hurdle model for playing time. I could not confirm whether one exists.

---

## Recommended concrete analysis designs (synthesis)

### Takeaway
A defensible pipeline for about 500 players over about 15 positions:
- (1) reliability first
- (2) shrink outcomes
- (3) hierarchical validity model with latent or measurement-error-aware covariates
- (4) out-of-sample incremental tests with player-level bootstrap and Freedman–Lane permutation
- (5) BH/BY FDR across the grid
- (6) selection-robustness checks

### Cited Findings
- Reliability and meta-metrics: [Franks et al. 2016](https://ideas.repec.org/a/bpj/jqsprt/v12y2016i4p151-165n3.html)
- EB shrinkage: [Efron & Morris 1975](https://www.medicine.mcgill.ca/epidemiology/hanley/bios602/MultilevelData/EfronMorrisJASA1975.pdf); [Brown 2008](https://doi.org/10.1214/07-aoas138)
- Measurement-error-aware incremental validity: [Westfall & Yarkoni 2016](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4816570/); [Frost & Thompson 2000](https://ideas.repec.org/a/bla/jorssa/v163y2000i2p173-189.html)
- FDR control: [Benjamini & Hochberg 1995](https://www.dcscience.net/Benjamini-Hochberg-1995-FDR.pdf)
- Selection: [Heckman 1979](https://www.econometricsociety.org/publications/econometrica/1979/01/01/sample-selection-bias-specification-error); [Wolfson et al. 2011](https://experts.umn.edu/en/publications/the-quarterback-prediction-problem-forecasting-the-performance-of/)
- Sprint curves: [Ramsay & Silverman 2005](https://link.springer.com/book/10.1007/b98888); [Samozino et al. 2016](https://hal.univ-reunion.fr/hal-01389134)

### Inferences
- **Design A: Reliability audit (do this first).**
  - For each combine and tracking metric, compute the ICC between attempts (where available). For each NFL outcome, compute split-half reliability vs snaps.
  - Produce a "reliability vs opportunity" curve, plus Franks-style stability (year t vs t+1) and discrimination.
  - Drop or flag outcomes with low reliability at typical snap counts.
- **Design B: Shrunk outcomes + hierarchical validity model.**
  - Fit an outcome model with exposure offsets and position-group random intercepts and slopes for the standardized metric (z-scored within position, mass-adjusted).
  - Report the posterior of each slope with 90/95% intervals, and the population-level slope.
  - Pick one primary outcome per position family before looking at the data.
- **Design C: Incremental validity vs 40 time and draft pick.**
  - Nested models: M0 = mass + position + 40; M1 = M0 + new metric; M2 = M0 + log(pick); M3 = M2 + new metric.
  - Report partial r and ΔR² with player-level stratified bootstrap BCa CIs, and Freedman–Lane permutation p-values (≥10,000 permutations, within position).
  - Report cross-validated ΔRMSE or Δlog-loss using leave-one-draft-year-out folds.
  - Robustness checks:
    - SEM with a latent speed factor (40 splits + tracking v_max + shuttle) to address Westfall–Yarkoni residual confounding.
    - SIMEX or regression calibration using the attempt-ICC reliability of the 40.
- **Design D: Curve-based metrics.**
  - Fit mono-exponential (v_max, τ) per rep, and/or registered-curve FPCA within position group.
  - Test whether τ or FPC2 (acceleration shape) adds beyond v_max and the 40 using Design C.
  - Keep the number of curve features at 2–4 to respect n≈33 per position.
- **Design E: Selection-robustness.**
  - Repeat the key estimates with (i) an all-draftee opportunity outcome, (ii) a hurdle model, (iii) IPW for being observed, and (iv) a Heckman two-step with an explicit exclusion restriction, if a credible one exists.
  - If the conclusions disagree across these, report that rather than choosing one.
- **Design F: Multiplicity and reporting.**
  - Define families (metric × position-group × primary outcome). Apply BH at q = 0.10 or 0.05, or BY if dependence is a concern.
  - Report all estimates (not just significant ones) in a forest plot with shrunk position-level effects.
  - Power caveat: with about 33 players per position, only large correlations are detectable per position. This is a general property of sample size and was not computed from any source here. That is a further reason to pool hierarchically.

### Gaps
- Not verified in this session (confirm before citing): Efron & Tibshirani (1993); Gelman & Hill (2007); Benjamini & Yekutieli (2001); Fuller (1987); Efron (2010); Ramsay, Hooker & Graves (2009); Bürkner (2017).
- I found no peer-reviewed literature applying FDA, measurement-error correction or Heckman selection specifically to NFL combine/tracking data, so the designs above are adaptations from general statistics.
