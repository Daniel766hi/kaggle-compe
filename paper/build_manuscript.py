"""Assemble the full manuscript draft (.docx) and auto-fill Results from model outputs.

    python build_manuscript.py            # uses model/outputs/       (your real final run)
    python build_manuscript.py --demo     # uses model/outputs_demo/  (layout preview, stamped DEMO)

Text sections are DRAFT wording to rewrite in your own words. Results tables and figures are
filled from the pipeline outputs; interpretation, Discussion, Conclusion and Abstract findings
are left for you. Yellow = you must write/fill.  Red = guidance, delete before submission.
"""
import re
import sys
from pathlib import Path

import pandas as pd
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_COLOR_INDEX
from docx.shared import Cm, Pt, RGBColor

HERE = Path(__file__).resolve().parent
MODEL = HERE / "model"
sys.path.insert(0, str(MODEL))
from common import DEMO_STAMP as STATUS_STAMP, POLICIES, SPIKE_THRESHOLD, UNCERTAINTIES  # noqa: E402

DEMO = "--demo" in sys.argv
OUT = MODEL / ("outputs_demo" if DEMO else "outputs")
DST = HERE / ("Manuscript_DRAFT_layout_DEMO.docx" if DEMO else "Manuscript_DRAFT.docx")
RED = RGBColor(0xC0, 0, 0)

doc = Document()
doc.styles["Normal"].font.name = "Times New Roman"
doc.styles["Normal"].font.size = Pt(11)
for s in doc.sections:
    s.left_margin = s.right_margin = s.top_margin = s.bottom_margin = Cm(2.5)


# ------------------------------------------------------------------ helpers
def note(t):
    r = doc.add_paragraph().add_run("GUIDE: " + t)
    r.italic = True; r.font.size = Pt(9.5); r.font.color.rgb = RED


def para(t, style=None):
    """Plain text; [[...]] becomes a yellow placeholder."""
    p = doc.add_paragraph(style=style)
    for i, chunk in enumerate(re.split(r"\[\[|\]\]", t)):
        r = p.add_run(chunk if i % 2 == 0 else f"[{chunk}]")
        if i % 2:
            r.font.highlight_color = WD_COLOR_INDEX.YELLOW
    return p


def write_here(t):
    para(f"[[{t}]]")


def demo_banner():
    text = ("DEMO - PLACEHOLDER PARAMETERS - NOT RESULTS - DO NOT USE" if DEMO else STATUS_STAMP)
    if text:
        r = doc.add_paragraph().add_run(text)
        r.bold = True; r.font.color.rgb = RED


def caption(t):
    p = doc.add_paragraph()
    r = p.add_run(t); r.bold = True; r.font.size = Pt(10)
    demo_banner()


def table(df, fmt=3, index=True, font=8.5):
    df = df.reset_index() if index else df
    t = doc.add_table(rows=1, cols=len(df.columns))
    t.style = "Light Grid Accent 1"
    for j, c in enumerate(df.columns):
        t.rows[0].cells[j].text = str(c)
    for _, row in df.iterrows():
        cells = t.add_row().cells
        for j, v in enumerate(row):
            if isinstance(v, float):
                v = f"{v:,.{fmt}f}" if abs(v) < 1e5 else f"{v:,.0f}"
            cells[j].text = str(v)
    for row in t.rows:
        for c in row.cells:
            for p in c.paragraphs:
                for r in p.runs:
                    r.font.size = Pt(font)
    doc.add_paragraph()


def read(name, **kw):
    f = OUT / name
    return pd.read_csv(f, comment="#", **kw) if f.exists() else None


def figure(name, width=15.5):
    f = OUT / name
    if f.exists():
        doc.add_picture(str(f), width=Cm(width))
    else:
        write_here(f"Figure missing: run the pipeline to create {name}")


def missing(name):
    write_here(f"Output {name} not found. Run `python run_all.py 5000` in paper/model first.")


# ================================================================== TITLE
t = doc.add_paragraph(); t.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = t.add_run("Programme-Driven Demand Shocks in Food Supply Chains: A System Dynamics and "
              "Machine-Learning Scenario Discovery Analysis of Indonesia's Free Nutritious Meals "
              "Programme and the Egg and Broiler Supply Chain")
r.bold = True; r.font.size = Pt(14)
for line in ["[[Your full name]]", "[[Affiliation]], Yogyakarta, Indonesia", "Corresponding author: [[email]]"]:
    p = para(line); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
demo_banner()
note("Everything in this document is a DRAFT. Rewrite all prose in your own words, verify every citation "
     "against the original source, fill every yellow placeholder from your own final run, and delete all red "
     "guidance before submission. Disclose AI assistance in the Declarations.")

# ================================================================== ABSTRACT
doc.add_heading("Abstract", 1)
note("Write the Findings sentence last, from your Results. 200–250 words in total.")
for lab, txt in [
    ("Purpose", "Indonesia's Free Nutritious Meals programme (MBG) creates a large, fast and price-inelastic "
                "public demand for eggs and broiler meat. This study examines when such a programme-driven demand "
                "shock destabilises food prices and which procurement and roll-out policies keep prices stable."),
    ("Design/methodology/approach", "A system dynamics model of the egg and broiler supply chains, including "
                "kitchen roll-out, biological production delays, farmer investment and price formation, was "
                "calibrated to public data. [[N]] scenarios were simulated with and without the programme, and "
                "machine-learning scenario discovery (classification trees, random forests, SHAP and PRIM) was used "
                "to identify the conditions under which programme-attributable price spikes occur."),
    ("Findings", "[[Your 2–3 main findings, with numbers from your final run]]"),
    ("Research limitations/implications", "[[e.g. national aggregation; parameter uncertainty in farmer behaviour]]"),
    ("Practical implications", "[[Concrete recommendations that follow from your results]]"),
    ("Originality/value", "[[Only after your literature check confirms it]] To the author's knowledge, this is the "
                "first quantitative dynamic analysis of how a national school-meals programme transmits demand "
                "shocks to food prices, and the first application of scenario discovery to this problem."),
]:
    p = doc.add_paragraph(); p.add_run(lab + ": ").bold = True
    for i, chunk in enumerate(re.split(r"\[\[|\]\]", txt)):
        rr = p.add_run(chunk if i % 2 == 0 else f"[{chunk}]")
        if i % 2:
            rr.font.highlight_color = WD_COLOR_INDEX.YELLOW
p = doc.add_paragraph(); p.add_run("Keywords: ").bold = True
p.add_run("system dynamics; scenario discovery; machine learning; food supply chain; demand shock; "
          "school meals programme; Indonesia")

# ================================================================== 1 INTRODUCTION
doc.add_heading("1. Introduction", 1)
note("Draft wording built from sources found by web search on 7 Nov 2026. Replace news citations with "
     "primary sources (BPS releases, BGN statements) wherever possible, and check every figure.")
para("Large public food programmes do more than feed their beneficiaries; they also change the markets they buy "
     "from. Indonesia's Free Nutritious Meals programme (Makan Bergizi Gratis, MBG), launched in January 2025, is "
     "one of the largest public food procurement programmes in the world. By the end of 2025 the National "
     "Nutrition Agency (Badan Gizi Nasional, BGN) reported 19,188 operational meal-preparation units (Satuan "
     "Pelayanan Pemenuhan Gizi, SPPG), and it targeted 82.9 million beneficiaries by mid-2026 [[cite BGN / "
     "Investortrust, 2025–2026]]. The programme budget was reported to rise from Rp 171 trillion in 2025 to "
     "Rp 335 trillion in 2026 [[cite primary budget source]].")
para("Eggs and broiler meat are core protein items on MBG menus. Unlike household demand, programme demand is "
     "set by menus and roll-out targets rather than by price, and it grows as fast as new kitchens open. Supply, "
     "in contrast, adjusts slowly: laying hens take roughly [[18–20]] weeks to reach point of lay, and farmers "
     "expand flocks on the basis of expected prices and margins [[cite poultry source]]. A fast, price-inelastic "
     "increase in demand meeting a slow, biologically delayed supply response is a classic setting for price "
     "overshoot and commodity cycles (Meadows, 1970; Sterman, 2000).")
para("Early evidence suggests that this tension is already visible but its cause is disputed. Statistics "
     "Indonesia (BPS) attributed part of the October 2025 inflation in eggs and broiler meat to demand from MBG "
     "kitchens [[cite BPS release; Katadata/Kontan/Bisnis, Nov 2025]], and national average egg prices were "
     "reported above the government reference price (HAP) from October 2025 [[verify and cite]]. The Ministry of "
     "Agriculture and the National Food Agency (Bapanas), however, described the movements as mainly seasonal and "
     "MBG demand as still too small to matter [[cite Bisnis, Nov 2025; Republika, Dec 2025]]. BGN has also stated "
     "that at least 1,500 additional layer farmers are needed in 2026 to keep egg supply stable [[cite]]. At the "
     "same time, the programme has faced operational strain, including reported food-safety incidents and the "
     "suspension of 1,256 SPPGs [[cite primary source]], and studies report that procurement often runs through "
     "intermediaries or single suppliers rather than local farmer groups [[cite IPB study; Central Java study]].")
para("These observations raise questions that statistical analysis of short price series cannot settle on its "
     "own: how much of the price movement is caused by the programme rather than by seasonal or external shocks; "
     "under which conditions programme demand produces a severe price spike; and which policies — the speed of "
     "roll-out, the sourcing structure, advance contracting with farmers or flexible menus — reduce that risk. "
     "Answering them requires a model that captures feedback and delays across the supply chain, and an analysis "
     "that explores many plausible futures rather than a single forecast.")
para("Existing research does not yet provide this. Studies of MBG to date are mainly qualitative or local "
     "[[cite]]; international work on school feeding shows that large programmes can move food prices "
     "(Handbury & Moshary, NBER w29384) and that local effects depend on procurement scale and market efficiency "
     "[[cite Ghana HGSF evaluation]], but does not model the supply-side dynamics. System dynamics studies of "
     "poultry supply chains explain endogenous price instability [[cite Indonesian broiler SD study, 2024; Aboah "
     "& Enahoro, 2022]] but do not consider programme-driven demand. Scenario discovery, which applies machine "
     "learning to large simulation ensembles to find decision-relevant conditions (Bryant & Lempert, 2010; "
     "Kwakkel, 2017), has rarely been applied to food supply chain policy in developing economies [[confirm with "
     "your gap table]].")
para("This study addresses three research questions:")
for q in ["RQ1: How does the MBG roll-out propagate through Indonesia's egg and broiler supply chains to market "
          "prices and household consumption over time?",
          "RQ2: Under which combinations of uncertain conditions does the programme cause severe programme-"
          "attributable price spikes?",
          "RQ3: Which roll-out and procurement policies reduce spike risk while maintaining programme coverage "
          "and cost?"]:
    para(q, style="List Number")
para("To answer them, a system dynamics model was developed, calibrated to public data and validated, and then "
     "run as an exploratory ensemble in which every scenario is simulated both with and without the programme. "
     "Machine-learning classifiers, SHAP values and the Patient Rule Induction Method (PRIM) were applied to the "
     "results to identify spike conditions, derive early-warning indicators and compare policies.")
para("The study makes three contributions. First, it provides [[to the author's knowledge, the first]] "
     "quantitative dynamic analysis of how a national school-meals programme transmits demand shocks to food "
     "prices, separating programme effects from exogenous shocks through a counterfactual design. Second, it "
     "demonstrates how system dynamics and machine-learning scenario discovery can be combined to produce "
     "interpretable spike conditions and early-warning rules. Third, it offers evidence-based recommendations for "
     "the design of large public food procurement programmes. Section 2 reviews related literature, Section 3 "
     "describes the model and analysis, Section 4 presents the results, Section 5 discusses them, and Section 6 "
     "concludes.")

# ================================================================== 2 LITERATURE
doc.add_heading("2. Literature Review", 1)
note("This section is an OUTLINE, not prose: a literature review must come from papers you have actually read. "
     "Read the sources in literature_reading_list.md, then write 2–4 paragraphs per subsection in your own "
     "words. End each subsection with what is missing, and close with the gap table.")
for h, pts in [
    ("2.1 Public food procurement and school meals programmes", [
        "Purpose and scale of school feeding programmes (WFP, Brazil PNAE, India PM-POSHAN, home-grown school feeding).",
        "Market effects: Handbury & Moshary (US retail prices); Ghana HGSF evaluation (effects depend on procurement scale and market efficiency); HGSF supply-chain models paper.",
        "MBG studies so far: procurement via intermediaries (IPB study), closed vs open supplier systems (Central Java study), CELIOS policy note (May 2026).",
        "Gap: mostly descriptive or econometric; no dynamic supply-side model."]),
    ("2.2 Demand shocks, biological lags and commodity cycles", [
        "Commodity production cycles and supply-line misperception (Meadows, 1970; Sterman, 2000).",
        "Biological lags and egg prices: Mitchell, Thompson & Malone (2024) on HPAI.",
        "Endogenous price fluctuation and price transmission in poultry (Pakistan studies).",
        "Gap: shocks studied are disease or seasonal, not programme-driven demand."]),
    ("2.3 System dynamics in poultry and food security", [
        "Indonesian broiler SD study (2024): live-bird price instability arises from system structure — closest prior work; state clearly how yours differs (eggs + broilers, programme demand, policy levers, ML).",
        "Aboah & Enahoro (2022): Ghana backyard poultry SD model.",
        "Indonesian Vensim food-security models (mostly rice): Aprillya & Suryani; Suryani et al.; Widyawati et al.",
        "Gap: no SD model of programme demand; validation often limited; single-scenario analysis."]),
    ("2.4 Scenario discovery and machine learning on simulation models", [
        "PRIM (Friedman & Fisher, 1999); scenario discovery (Bryant & Lempert, 2010); improvements (Kwakkel & Jaxa-Rozen, 2016); EMA Workbench (Kwakkel, 2017).",
        "Dynamic/behaviour-based scenario discovery (Steinmann et al., 2020); copper SD + PRIM (Kwakkel, Auping & Pruyt).",
        "Interpretable ML: SHAP (Lundberg & Lee, 2017); rule extraction (REDS).",
        "Gap: rarely applied to food supply chains or developing-economy public programmes."]),
]:
    doc.add_heading(h, 2)
    for x in pts:
        doc.add_paragraph(x, style="List Bullet")
    write_here("Write this subsection after reading the sources")
doc.add_heading("2.5 Research gap", 2)
caption("Table 1. Positioning of this study relative to prior work")
table(pd.DataFrame([
    ["[[Author, year]]", "[[ ]]", "[[ ]]", "[[Y/N]]", "[[Y/N]]", "[[Y/N]]"],
    ["[[Author, year]]", "[[ ]]", "[[ ]]", "[[Y/N]]", "[[Y/N]]", "[[Y/N]]"],
    ["This study", "Indonesia, MBG, eggs & broilers", "SD + ML scenario discovery", "Y", "Y", "Y"]],
    columns=["Study", "Context", "Method", "Programme demand", "Dynamic feedback", "Scenario discovery"]), index=False)

# ================================================================== 3 METHODS
doc.add_heading("3. Methodology", 1)
note("Draft wording that describes the model in paper/model/ as built. Update it to match every change you make.")
doc.add_heading("3.1 Research design", 2)
para("The study combines system dynamics (SD) simulation with machine-learning scenario discovery (Figure 1). An "
     "SD model of the egg and broiler supply chains under MBG was developed in Vensim, calibrated to public data "
     "and validated with structural and behavioural tests. The model was then run as an exploratory ensemble over "
     "uncertain parameters and alternative policies using PySD (Houghton & Siegel, 2015). Classifiers, SHAP values "
     "(Lundberg & Lee, 2017) and PRIM (Friedman & Fisher, 1999; Bryant & Lempert, 2010), implemented with the EMA "
     "Workbench (Kwakkel, 2017), were used to identify the conditions under which the programme produces severe "
     "price increases, and policies were compared on a common set of scenarios with paired non-parametric tests.")
write_here("Figure 1. Research framework — draw it")
doc.add_heading("3.2 Model structure", 2)
para("The model has four interacting sectors simulated weekly from January 2024 to December 2029 (312 weeks; "
     "time step 0.125 weeks). Its causal structure is shown in Figure 2 and its stock-and-flow structure in "
     "Figure 3; all equations are listed in Appendix A.")
for txt in [
    "Programme sector. Planned kitchens (SPPG) follow a logistic (S-shaped) roll-out whose final size, midpoint "
    "and steepness were fitted so that modelled operational kitchens reproduce BGN's reported counts (Section 3.4). "
    "Kitchens open after an opening delay and can be suspended. The weekly suspension fraction "
    "rises when the opening rate exceeds a sustainable opening capacity, representing strain on supervision, "
    "staff and suppliers during rapid scaling (reinforcing loop R1). Suspended kitchens reopen after a "
    "reinstatement time. Programme demand for eggs and chicken equals beneficiaries served multiplied by the menu "
    "quantity per beneficiary.",
    "Egg (layer) sector. Pullets are placed and mature into laying hens through a third-order rearing delay. Hens "
    "leave the flock through culling and disease outbreaks. Farmers place pullets to replace expected losses and "
    "to close the gap between desired and actual flock size, with a partial correction for pullets already in "
    "rearing (supply-line weight; Sterman, 2000). Desired flock size responds to expected margin, formed by "
    "smoothing market price over an expectation delay (balancing loop B1 with delay). Placements are limited by "
    "hatchery capacity.",
    "Broiler sector. Day-old chicks are placed and harvested after grow-out. Placements follow smoothed demand, "
    "inventory correction and expected margin, limited by day-old-chick supply.",
    "Market and price formation. For each commodity, market inventory accumulates production and is depleted by "
    "sales and spoilage; programme kitchens are served before households when stock is short. Household demand "
    "responds to price through a constant own-price elasticity (balancing loop B2). Price adjusts toward an "
    "indicated price that rises when inventory coverage is below normal and is pulled toward unit cost plus a "
    "normal margin, bounded by a maximum relative price that represents imports, substitutes and market "
    "operations. Unit cost depends on feed price, which rises with total flock size (balancing loop B3) and with "
    "exogenous feed-price shocks."]:
    para(txt)
write_here("Figure 2. Causal loop diagram (draw in Vensim)")
write_here("Figure 3. Stock-and-flow diagram (draw in Vensim)")
doc.add_heading("3.3 Policies", 2)
caption("Table 2. Policy levers")
table(pd.DataFrame([
    ["P0 Baseline", "Current roll-out; cooperative sourcing share 0.1; no forward contracts; fixed menu"],
    ["P1 Phased roll-out", "Roll-out steepness × 1.75, i.e. a more gradual S-curve [[justify from BGN plans]]"],
    ["P2 Cooperative sourcing", "Direct purchase share from farmer groups 0.6 (reduces intermediary mark-up)"],
    ["P3 Forward contracts", "80% of future programme demand contracted 20 weeks ahead"],
    ["P4 Menu flexibility", "Up to 50% substitution when relative price > 1.15"],
    ["P5 Combined", "P2 + P3 + P4"]], columns=["Policy", "Implementation"]), index=False)
doc.add_heading("3.4 Data and parameters", 2)
para("Prices. Monthly retail prices of chicken eggs and chicken meat were taken from the World Food Programme's "
     "Indonesia food price dataset on the Humanitarian Data Exchange (WFP, [[access date]]; CC BY-IGO), which "
     "covers about 200 markets. Because WFP publishes no recent national average and the set of reporting markets "
     "varies, each market's price was expressed relative to its own 2024 mean, and the national index for each "
     "month is the median of these relatives. Months with fewer than 100 reporting markets, and the incomplete "
     "latest month, were excluded, leaving 29 monthly observations (January 2024 to October 2026). Baseline prices "
     "were set to the 2024 mean of monthly national medians (Rp 28,140/kg for eggs; Rp 35,704/kg for chicken).")
para("Programme roll-out. Reported numbers of operational SPPG and beneficiaries were compiled from BGN releases "
     "and press reports for August 2025 to September 2026 [[cite each; replace secondary sources]]. The roll-out "
     "parameters were estimated by least squares so that modelled operational kitchens match these counts. "
     "Beneficiaries per kitchen (about 2,850) were derived from the same reports. Menu quantities were set from "
     "planning figures reported by Bapanas, BGN and the Ministry of Agriculture (about 0.11–0.17 kg of egg and "
     "0.08–0.26 kg of chicken per beneficiary per week) [[cite]], and are treated as uncertain. Kitchen-suspension "
     "parameters were fitted to BGN's report that 8,182 SPPG had been suspended at some point and 2,213 remained "
     "inactive by the end of May 2026 [[cite]]; the fitted weekly suspension hazard is about 0.4% and the mean "
     "reinstatement time about 15 weeks. Because suspensions in practice came largely in enforcement waves (for "
     "example, 1,256 SPPG in eastern Indonesia from 1 April 2026 for missing hygiene certificates), a constant "
     "hazard is an approximation.")
para("Supply and demand parameters. Baseline production was derived from Bapanas' 2025 food balance projections "
     "(egg production 6.52 Mt, chicken meat 4.25 Mt, with stated growth rates over 2024) [[cite; verify with BPS]]. "
     "Household own-price elasticities were set from QUAIDS estimates on SUSENAS data (eggs about −0.7, poultry about "
     "−1.55; Khoiriyah et al., 2024, and the Bengkulu study) [[verify]]. Layer and broiler parameters (point of lay "
     "at about 18 weeks, laying period of about 65 weeks, hen-day production of about 84.5%, harvest at about five "
     "weeks, carcass yield about 1.37 kg per bird, grow-out mortality 5%) follow Indonesian farm studies and breed "
     "standards [[cite]]. Feed is 65–70% of production cost (Kementan) [[cite]]. Trader mark-ups follow BPS trade and "
     "transport margins for eggs (13–27%, 2017–2021), and day-old-chick capacity reflects documented oversupply "
     "(production about 1.2 times demand in 2020) [[cite]]. Two kitchen-operation parameters without public data "
     "(opening delay and sustainable opening capacity) are treated as uncertain. Appendix B lists every parameter "
     "with its value and source.")
doc.add_heading("3.5 Validation", 2)
para("Following Barlas (1996) and Sterman (2000), the model was subjected to dimensional consistency checks; "
     "extreme-condition tests (no programme, ten-fold programme demand, loss of all laying hens, no hatchery "
     "expansion, doubled feed price, instantaneous roll-out); an integration-error test comparing time steps of "
     "0.125 and 0.0625 weeks; a parameter-recovery test applying the calibration procedure to synthetic data with "
     "known parameters; and behaviour reproduction against historical prices, assessed with MAPE, R² and Theil "
     "inequality statistics.")
para("Because the model contains no seasonal demand, seasonality was removed from the price data before "
     "calibration. Using the WFP national series for 2007–2023 (pre-programme; March 2020 to December 2021 "
     "excluded), the log ratio of price to its centred 12-month moving average was regressed on calendar-month "
     "dummies and on the shares of the 30 days before and after Idul Fitri falling in each month, with HAC "
     "standard errors. The fitted seasonal factors were divided out of the 2024–2026 series. The remaining "
     "investment sensitivities of layer and broiler farmers were then estimated jointly on the seasonally adjusted "
     "egg and chicken series by minimising the sum of squared errors (Nelder–Mead, four starting points). Two "
     "further parameters, the price-expectation delay and the sensitivity of price to inventory coverage, were "
     "found not to be identifiable: the fit error changed little across wide ranges of either (Table 4e). They "
     "were therefore fixed (8 weeks and 1.0) [[justify]] and explored over wide ranges in the ensemble.")
doc.add_heading("3.6 Exploratory ensemble and outcome indicators", 2)
para(f"[[N]] scenarios were drawn by Latin Hypercube sampling over {len(UNCERTAINTIES)} uncertain parameters "
     "(Table 3). Each policy was run on the same scenarios (common random numbers), giving a paired design, and each "
     "scenario was also run without the programme. Price effects were measured as the difference between the two "
     "runs, so that movements caused by exogenous shocks or seasonality are not attributed to the programme. "
     "Outcome indicators were the peak programme-attributable egg and chicken price rise, weeks above the "
     "threshold, mean household consumption loss, farmers' margin volatility, protein cost per portion and "
     f"programme coverage in the final year. A run was labelled a spike if the programme-attributable price rise "
     f"in either commodity exceeded {SPIKE_THRESHOLD * 100:.0f} percentage points, because [[justification]].")
caption("Table 3. Uncertain parameters and ranges [[replace placeholder ranges with sourced ones]]")
table(pd.DataFrame([[k, lo, hi, "[[source/justification]]"] for k, (lo, hi) in UNCERTAINTIES.items()],
                   columns=["Parameter", "Low", "High", "Justification"]), index=False)
doc.add_heading("3.7 Scenario discovery and early warning", 2)
para("Using baseline-policy runs, four classifiers (logistic regression, a depth-3 decision tree, random forest "
     "and gradient boosting) were trained to predict spikes from the uncertain parameters and evaluated by "
     "stratified five-fold cross-validation. The decision tree provides readable rules; SHAP values on the random "
     "forest quantify each parameter's contribution and direction; PRIM identifies a region of the uncertainty "
     "space with high spike density (the box with the highest coverage at density ≥ 0.8, reporting dimensions "
     "restricted by at least 10% of their range). Results were compared with a one-at-a-time sensitivity analysis. "
     "An early-warning classifier was trained on indicators observable 13 weeks after programme start (relative "
     "prices, inventory coverage, growth in pullet placements, kitchen opening rate, share of suspended kitchens "
     "and feed price).")
doc.add_heading("3.8 Policy comparison", 2)
para("For each policy, spike probability is reported with Wilson 95% confidence intervals, and the median and "
     "10th/90th percentiles of each outcome are reported. Each policy is compared with P0 on the same scenarios "
     "with the Wilcoxon signed-rank test (Holm-corrected; matched-pairs rank-biserial correlation as effect size), "
     "spike occurrence with an exact McNemar test, and all policies jointly with the Friedman test.")

# ================================================================== 4 RESULTS (auto-filled)
doc.add_heading("4. Results", 1)
note("Tables and figures below are filled automatically from " + str(OUT.relative_to(HERE)) +
     ". Under each one, describe what it shows (facts only); interpret in Section 5.")
doc.add_heading("4.1 Validation", 2)
v = read("validation_tests.csv")
if v is not None:
    caption("Table 4. Validation tests"); table(v, index=False)
else:
    missing("validation_tests.csv")
sr = read("seasonal_regression.csv")
if sr is not None:
    keep = sr[sr["term"].isin(["eid_pre", "eid_post", "m12", "R2", "n_obs"])]
    caption("Table 4b. Pre-programme seasonal regression (selected terms)"); table(keep, fmt=4, index=False)
rf = MODEL / "data" / "rollout_fit.csv"
if rf.exists():
    caption("Table 4c. Roll-out fit: reported vs modelled operational SPPG")
    table(pd.read_csv(rf), fmt=3, index=False)
ip = read("identifiability_profile.csv")
if ip is not None:
    caption("Table 4e. Identifiability profile: fit error (SSE) when one fixed parameter is varied")
    table(ip, fmt=6, index=False)
cp = MODEL / "data" / "calibrated_parameters.csv"
if cp.exists():
    caption("Table 4d. Calibrated parameters (best of four starts)")
    table(pd.read_csv(cp, index_col=0), fmt=4)
b = read("behaviour_reproduction.csv", index_col=0)
if b is not None:
    caption("Table 5. Behaviour reproduction (fit to historical prices)"); table(b, fmt=4)
    caption("Figure 4. Simulated vs observed (seasonally adjusted) prices"); figure("fig_behaviour_reproduction.png", 15.5)
else:
    write_here("Behaviour reproduction: add real price data, run s02_validation.py (Table 5, Figure 4)")
write_here("Describe validation results")

doc.add_heading("4.2 Baseline dynamics", 2)
caption("Figure 5. Baseline dynamics with and without the programme"); figure("fig_baseline_dynamics.png")
write_here("Describe timing and size of the price response, overshoot/oscillation, household consumption")

doc.add_heading("4.3 When do programme-attributable spikes occur?", 2)
cb = read("sd_classifier_benchmark.csv", index_col=0)
if cb is not None:
    caption("Table 6. Classifier performance (5-fold cross-validation)")
    table(cb[[c for c in cb.columns if c.endswith("_mean")]])
else:
    missing("sd_classifier_benchmark.csv")
caption("Figure 6. SHAP summary (random forest)"); figure("fig_shap_summary.png", 13)
pb = read("sd_prim_box.csv", index_col=0)
if pb is not None:
    caption("Table 7. PRIM box: conditions with high spike density"); table(pb)
    figure("fig_prim_tradeoff.png", 10)
else:
    missing("sd_prim_box.csv")
rules = OUT / "sd_cart_rules.txt"
if rules.exists():
    caption("Box 1. Decision-tree rules")
    p = doc.add_paragraph(); rr = p.add_run(rules.read_text()); rr.font.name = "Courier New"; rr.font.size = Pt(7.5)
caption("Figure 7. One-at-a-time sensitivity (for comparison)"); figure("fig_oat_tornado.png", 12)
write_here("Describe which conditions drive spikes, the PRIM box (coverage/density), and what OAT misses")

doc.add_heading("4.4 Early-warning indicators", 2)
ew = read("ew_classifier_benchmark.csv", index_col=0)
if ew is not None:
    caption("Table 8. Early-warning classifier (indicators at week 13 of the programme)"); table(ew)
ewr = OUT / "ew_rules.txt"
if ewr.exists():
    p = doc.add_paragraph(); rr = p.add_run(ewr.read_text()); rr.font.name = "Courier New"; rr.font.size = Pt(7.5)
write_here("Translate the rules into monitoring thresholds")

doc.add_heading("4.5 Policy comparison", 2)
ps = read("policy_summary.csv", index_col=0)
if ps is not None:
    cols = ["spike_prob", "spike_ci_low", "spike_ci_high", "peak_egg_price_median", "peak_egg_price_p90",
            "peak_chicken_price_median", "hh_egg_loss_median", "mean_cost_per_portion_median",
            "mean_coverage_last52_median"]
    caption("Table 9. Policy outcomes across scenarios"); table(ps[[c for c in cols if c in ps.columns]], font=7.5)
wx = read("policy_wilcoxon_vs_P0.csv")
if wx is not None:
    w = wx[wx["outcome"].isin(["peak_egg_price", "peak_chicken_price", "hh_egg_loss", "mean_cost_per_portion"])]
    caption("Table 10. Paired comparison with P0 (Wilcoxon signed-rank, Holm-corrected)")
    table(w[["outcome", "policy", "median_diff", "rank_biserial", "p_holm"]], fmt=4, index=False, font=7.5)
mc = read("policy_mcnemar_spike.csv", index_col=0)
if mc is not None:
    caption("Table 11. Change in spike occurrence vs P0 (exact McNemar)"); table(mc, fmt=4)
caption("Figure 8. Policy comparison"); figure("fig_policy_comparison.png")
caption("Figure 9. Cost vs spike-risk trade-off"); figure("fig_policy_tradeoff.png", 11)
write_here("Describe which policies reduce spike risk, by how much, and at what cost")

# ================================================================== 5–6
doc.add_heading("5. Discussion", 1)
note("Interpretation is the core intellectual contribution and must be yours.")
for h, g in [("5.1 Why the system behaves this way", "Link results to loops R1, B1–B3 and the delays"),
             ("5.2 Comparison with previous studies", "Agree/disagree with Section 2 sources; the BPS vs Bapanas debate"),
             ("5.3 Policy implications", "Specific, neutral, evidence-based recommendations for BGN, Bapanas, local governments, cooperatives"),
             ("5.4 Methodological contribution", "What the counterfactual design and scenario discovery revealed that OAT/single scenarios would not"),
             ("5.5 Limitations and future research", "National aggregation, parameter uncertainty, no regional or trade detail, other commodities")]:
    doc.add_heading(h, 2); write_here(g)
doc.add_heading("6. Conclusion", 1)
write_here("Answer RQ1–RQ3 directly in 300–400 words; restate contributions; one sentence on future work")

# ================================================================== DECLARATIONS / REFS
doc.add_heading("Declarations", 1)
for lab, txt in [("Funding", "This research received no external funding."),
                 ("Competing interests", "The author declares no competing interests."),
                 ("Data and code availability", "The model, code and data are available at [[GitHub/Zenodo link]]."),
                 ("Use of AI tools", "[[Describe honestly, following the journal's policy, how an AI assistant was used "
                                     "(e.g. model and code development, structuring and drafting text) and confirm that "
                                     "the author verified all content and takes full responsibility for it.]]")]:
    p = doc.add_paragraph(); p.add_run(lab + ": ").bold = True
    for i, chunk in enumerate(re.split(r"\[\[|\]\]", txt)):
        rr = p.add_run(chunk if i % 2 == 0 else f"[{chunk}]")
        if i % 2:
            rr.font.highlight_color = WD_COLOR_INDEX.YELLOW

doc.add_heading("References", 1)
note("Verify every entry against the original. Add the sources you actually read; remove any you do not cite.")
for ref in [
    "Barlas, Y. (1996). Formal aspects of model validity and validation in system dynamics. System Dynamics Review, 12(3), 183–210.",
    "Bryant, B. P., & Lempert, R. J. (2010). Thinking inside the box: A participatory, computer-assisted approach to scenario discovery. Technological Forecasting and Social Change, 77(1), 34–49.",
    "Friedman, J. H., & Fisher, N. I. (1999). Bump hunting in high-dimensional data. Statistics and Computing, 9(2), 123–143.",
    "Handbury, J., & Moshary, S. (2021). School food policy affects everyone: Retail responses to the National School Lunch Program. NBER Working Paper 29384.",
    "Houghton, J., & Siegel, M. (2015). Advanced data analytics for system dynamics models using PySD. Proceedings of the 33rd International System Dynamics Conference.",
    "Kwakkel, J. H. (2017). The Exploratory Modeling Workbench. Environmental Modelling & Software, 96, 239–250.",
    "Kwakkel, J. H., & Jaxa-Rozen, M. (2016). Improving scenario discovery for handling heterogeneous uncertainties and multinomial classified outcomes. Environmental Modelling & Software, 79, 311–321.",
    "Lundberg, S. M., & Lee, S.-I. (2017). A unified approach to interpreting model predictions. Advances in Neural Information Processing Systems, 30.",
    "Meadows, D. L. (1970). Dynamics of Commodity Production Cycles. Wright-Allen Press.",
    "Steinmann, P., Auping, W. L., & Kwakkel, J. H. (2020). Behavior-based scenario discovery using time series clustering. Technological Forecasting and Social Change, 156, 120052.",
    "Sterman, J. D. (2000). Business Dynamics: Systems Thinking and Modeling for a Complex World. Irwin/McGraw-Hill.",
    "[[Mitchell, Thompson & Malone (2024) — complete after reading]]",
    "[[Aboah & Enahoro (2022), Agricultural Systems — complete after reading]]",
    "[[Indonesian broiler SD study (2024) — complete after reading]]",
    "[[MBG studies, BPS, BGN, Bapanas and news sources — complete with access dates]]"]:
    para(ref)

# ================================================================== APPENDICES
doc.add_page_break()
doc.add_heading("Appendix A. Model equations", 1)
text = (MODEL / "mbg_poultry.mdl").read_text().split("\\\\\\---///")[0].replace("{UTF-8}", "")
rows = []
for block in text.split("|"):
    m = re.match(r"\s*(.+?)=\s*\n\t(.+?)\n\t~\t(.*?)\n\t~\t(.*?)\s*$", block, re.S)
    if m:
        rows.append([x.strip() for x in m.groups()[:3]])
table(pd.DataFrame(rows, columns=["Variable", "Equation", "Units"]), index=False, font=7)
doc.add_heading("Appendix B. Parameters and sources", 1)
ps_ = pd.read_csv(MODEL / "data" / "parameter_sheet.csv").fillna("")
ps_["source"] = ps_["source"].replace("", "[to fill]")
table(ps_[["parameter", "model_value", "units", "tag", "source"]], index=False, font=7)

doc.save(DST)
print("saved", DST)
