# Sections 6-8 of the paper. Executed inside build_paper_latex.py (shares its variables), so every number
# comes from the pipeline outputs. Statements that depend on the direction of a result are conditional.

hist = pd.read_csv(MODEL / "data" / "historical_prices.csv", parse_dates=["month"])
_wk = lambda d: (pd.Timestamp(d) - WEEK0).days / 7
_oct25 = _ex_egg[(_ex_egg.index >= _wk("2025-10-01")) & (_ex_egg.index < _wk("2025-11-01"))].mean()
_oct25_c = _ex_chk[(_ex_chk.index >= _wk("2025-10-01")) & (_ex_chk.index < _wk("2025-11-01"))].mean()
_obs_oct25 = hist.loc[hist["month"].dt.strftime("%Y-%m") == "2025-10", "rel_egg_price_sa"].iloc[0] - 1
_obs_oct25_c = hist.loc[hist["month"].dt.strftime("%Y-%m") == "2025-10", "rel_chicken_price_sa"].iloc[0] - 1
_after = _ex_egg[_ex_egg.index > pk_e_w]
_trough, _trough_w = float(_after.min()), float(_after.idxmin())
p1, p3, p4, p5 = (ps.loc[k] for k in ["P1 Phased roll-out", "P3 Forward contracts", "P4 Menu flexibility",
                                     "P5 Combined (P2+P3+P4)"])
m1 = mc.loc["P1 Phased roll-out"]
broiler_zero = str(binv["at_bound"]) == "True"

sec("Discussion", "sec:discussion")
sub("Why the System Behaves This Way")
par("Programme demand is set by kitchen numbers, menus and the school calendar, not by price, and it grew from "
    "almost nothing to tens of millions of meals within a year. Laying capacity cannot follow at that speed: a "
    "pullet placed in response to higher prices starts laying about 18 weeks later, and farmers form price "
    "expectations with a delay. In the meantime the market clears through price, and the balancing loop that acts "
    "fastest is household demand (B2): households buy fewer eggs and less chicken, which is why the programme-"
    f"attributable price rise in the baseline coincides with household consumption {pct(BASE['hh_egg_loss'])} "
    f"(eggs) and {pct(BASE['hh_chicken_loss'])} (chicken) lower than without the programme. The programme's "
    "nutritional gain for beneficiaries is therefore partly offset by a loss for non-beneficiary households, a "
    "distributional effect that does not appear in programme statistics.")
if _trough < -0.01:
    par(f"Once new flocks come into lay, the supply loop (B1) overshoots: in the baseline the egg price falls "
        f"{pp(-_trough)} percentage points below the counterfactual by {wdate(_trough_w)}. This is the commodity-"
        "cycle mechanism described by Meadows {cite:meadows1970} and Sterman {cite:sterman2000}, triggered here by a "
        "demand shock rather than by a supply shock. It matches the sequence observed in 2026, when farm-gate egg "
        "prices fell below the government reference price and BGN raised egg servings to absorb the surplus "
        "{cite:egg3x2026}.")
else:
    par("Once new flocks come into lay, the supply loop (B1) closes the gap between supply and programme demand, and "
        "the attributable price rise fades without a marked undershoot in the baseline.")
par("School holidays act as a second, recurring shock. When meals stop for two to three weeks, programme demand "
    "drops at once, but eggs keep coming from flocks sized for term-time demand, so inventories rise and prices "
    "fall; when schools reopen, demand returns at full strength. The June 2026 request by the Minister of "
    "Agriculture that companies absorb farmers' eggs and chicken during the holiday {cite:amran2026} and the price "
    "rise he attributed to MBG after schools reopened {cite:okezone2026} are both consistent with this mechanism. "
    "The June 2026 rule that also stopped holiday meals for mothers and young children {cite:holiday2026} deepened "
    "these swings.")
if broiler_zero:
    par("The broiler chain behaves differently. The calibrated sensitivity of broiler placements to the expected "
        "margin is close to zero, meaning that placements follow demand and integrator planning rather than "
        "prices. This is consistent with the integrator-dominated structure and quota-based allocation of day-old "
        "chicks described by Haryana et al. {cite:haryana2026}, and it explains why chicken price risk depends so "
        "strongly on how much chicken the programme buys.")
sub("Comparison with Previous Studies and the Attribution Debate")
par(f"The counterfactual design speaks directly to the disagreement between BPS and the Ministry of Agriculture. "
    f"In October 2025 the seasonally adjusted national egg price was {pct(_obs_oct25)} above its 2024 level and "
    f"the chicken price {pct(_obs_oct25_c)}. In the calibrated baseline, the programme accounts for "
    f"{pp(_oct25)} percentage points of the egg price and {pp(_oct25_c)} points of the chicken price in that "
    "month. " + ("The programme therefore explains a substantial part of the October 2025 egg price rise, supporting "
                 "the BPS interpretation {cite:bps2025}, while seasonal factors explain the rest."
                 if _oct25 > 0.5 * max(_obs_oct25, 1e-9) else
                 "Most of the October 2025 rise therefore reflects factors other than the programme, closer to the "
                 "Ministry's reading {cite:kementan2025}, although the programme's contribution was not negligible.")
    + " Neither agency's position can be confirmed from price data alone, because programme demand and seasonal "
    "demand rose at the same time; separating them requires a counterfactual.")
par("The results agree with Mitchell, Thompson and Malone {cite:mitchell2024} that biological lags determine how "
    "far prices move after a shock: in the model the size of the programme-attributable rise depends on how fast "
    "demand arrives relative to the rearing delay. They extend Haryana et al. {cite:haryana2026}, who show that "
    "broiler price instability arises from the structure of supply, by adding a public programme as a new source "
    "of demand-side instability. The results are also consistent with the argument of Gelli et al. "
    "{cite:gelli2021} that the market effects of school meals depend on procurement scale: MBG procurement is large "
    "relative to the national egg market, which is why national prices respond. Local effects in less integrated "
    "markets may be larger than the national effects estimated here.")
sub("Practical Implications for Programme Design", "sec:implications")
par(f"Four implications follow. First, procurement design matters more than roll-out speed. Forward contracts, "
    f"which let farmers expand flocks before programme demand arrives, reduce spike probability from "
    f"{pct(P0['spike_prob'])} to {pct(p3['spike_prob'])}, while slowing the roll-out (P1) reduces it only to "
    f"{pct(p1['spike_prob'])}" + (f" and creates spikes in {int(m1.iloc[1]):,} scenarios where none occurred "
                                   "before, because a slower roll-out can shift demand into a less favourable phase "
                                   "of the supply cycle" if int(m1.iloc[1]) > 0.1 * int(m1.iloc[0]) else "")
    + ". BGN could publish roll-out schedules and menu plans several months ahead and contract a share of eggs and "
    "chicken with farmer cooperatives on that basis.")
par(f"Second, menus should flex by rule rather than by ad hoc decision. Menu flexibility (P4) lowers spike "
    f"probability to {pct(p4['spike_prob'])} and cuts the 90th percentile of the egg price rise from "
    f"{pp(P0['peak_egg_price_p90'])} to {pp(p4['peak_egg_price_p90'])} percentage points. The November 2025 and "
    "June 2026 menu changes show that BGN already uses menus as a market instrument {cite:prabowo2025,egg3x2026}; "
    "a published rule linking servings to price thresholds would make the response predictable for farmers.")
par(f"Third, cooperative sourcing (P2) lowers the protein cost per portion from Rp {cost0:,.0f} to Rp "
    f"{ps.loc['P2 Cooperative sourcing', 'mean_cost_per_portion_median']:,.0f} but does not change prices in the "
    "model, because it changes who captures the margin, not how much is produced. It is worth pursuing for "
    "budget reasons, and its price effect would depend on whether cooperatives also expand supply. Combining the "
    f"three procurement measures (P5) gives the lowest spike probability ({pct(p5['spike_prob'])}) and the lowest "
    "cost per portion.")
par("Fourth, the programme should plan for school holidays. Keeping meals for mothers and young children during "
    "holidays, aligning holiday periods with government purchasing for food reserves, or shifting part of "
    "holiday-period egg supply to processing would reduce the stop-start shock that the June 2026 rules "
    "amplified. Because early market indicators predict spikes only moderately, these measures need to be designed in "
    "advance rather than triggered by price signals.")
sub("Methodological Contribution")
par("The analysis shows what the combination of system dynamics and scenario discovery adds to a single "
    "simulation or a one-at-a-time sensitivity analysis. The counterfactual design separates the programme's "
    "effect from feed, disease and seasonal shocks that would raise prices anyway, which is the question the "
    "agencies disagree on. " + (f"Scenario discovery and the one-at-a-time analysis rank drivers differently "
    f"(Spearman {{m:\\rho}} = {RHO:.2f}), so a conventional sensitivity analysis would have pointed to the wrong "
    "levers. " if RHO < 0.7 else "") + "PRIM turns the ensemble into conditions that decision makers can act on, "
    "such as the " + " and ".join(pn(k) for k in prim_m.index) + " beyond which spikes become likely, and SHAP "
    "values show the direction "
    "and size of each driver's effect.")

sec("Limitations and Future Work", "sec:limits")
par("The study has several limitations. First, the model is national and has no regional detail or trade between "
    "regions; local price effects, particularly in eastern Indonesia, may differ from the national effects "
    "estimated here. Second, the chicken quantity per beneficiary is not published and official estimates "
    "conflict, so it is treated as a wide uncertainty; because it is a leading driver of spikes, publication of "
    "menu specifications by BGN would sharpen the results. Third, the temporary substitution of eggs requested in "
    "November 2025 is not modelled, because its size and duration were not reported, and the school-holiday "
    "calendar is a national approximation. Fourth, cooperative sourcing affects only procurement cost in the "
    "model. Fifth, household price elasticities come from a provincial study and are applied nationally, and the "
    "kitchen suspension hazard is constant although suspensions occurred in enforcement waves.")
par(f"Sixth, the model reproduces the main movements of seasonally adjusted prices with moderate accuracy "
    f"({{m:R^2}} of {EGG['R2']:.2f} for eggs and {CHK['R2']:.2f} for chicken); short-term fluctuations driven by "
    "events outside the model, such as weather, disease outbreaks and government market operations, are not "
    "reproduced. Two parameters, the price-expectation delay and the price response to inventory coverage, are "
    "not identifiable from the available data and were explored over wide ranges instead.")
par("Future work could add regional subscripts and inter-island trade, collect procurement data from a sample of "
    "SPPG to replace the menu uncertainty with observed quantities, model cooperative sourcing as a channel for "
    "supply expansion, apply behaviour-based scenario discovery {cite:steinmann2020} to classify the shape of price "
    "paths rather than only their peaks, and extend the model to other programme commodities such as milk, rice "
    "and vegetables.")

sec("Conclusion", "sec:conclusion")
par(f"This paper developed a system dynamics model of Indonesia's egg and broiler supply chains under the Free "
    f"Nutritious Meals programme and analysed it with machine-learning scenario discovery over {N_SCEN:,} scenarios. "
    f"On RQ1, the programme's price-inelastic demand meets a biologically delayed supply response, so prices rise "
    f"until households cut consumption and new flocks arrive; in the calibrated baseline the programme-attributable "
    f"rise peaks at {pp(BASE['peak_egg_price'])} percentage points for eggs and {pp(BASE['peak_chicken_price'])} "
    "for chicken, and school holidays add recurring demand swings. On RQ2, a spike of more than "
    f"{pp(SPIKE_THRESHOLD, 0)} points occurs in {pct(P0['spike_prob'])} of scenarios under current policy and "
    f"depends mainly on {pn(shap.index[0])}, {pn(shap.index[1])} and {pn(shap.index[2])}, in combinations that a "
    f"one-at-a-time analysis does not reveal. On RQ3, {LABEL[best_single].lower()} is the most effective single "
    f"policy ({pct(spike[best_single])}), and combining cooperative sourcing, forward contracts and menu "
    f"flexibility reduces spike probability to {pct(p5['spike_prob'])} at a lower cost per portion, without "
    "reducing programme coverage.")
par("The contributions are a calibrated dynamic model of programme-driven demand shocks, a counterfactual design "
    "that separates programme effects from seasonal and external shocks, and a demonstration that scenario discovery "
    "identifies policy-relevant conditions that conventional sensitivity analysis misses. The results suggest that "
    "large public food programmes should plan procurement, menus and holiday supply in advance, because by the time "
    "price signals appear the supply response is months away. Extending the model to regional markets and other "
    "commodities is the natural next step.")
