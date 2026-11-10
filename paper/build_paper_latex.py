"""Build the manuscript as a two-column LaTeX paper (A4, Times, numbered references) and compile it.

    python build_paper_latex.py                 # model/outputs/ -> latex/MBG_paper.tex and MBG_paper.pdf
    python build_paper_latex.py --outputs DIR   # build from another output folder (layout testing)

Layout follows the author's earlier SLR manuscript: title block, one-paragraph abstract with keywords,
1 Introduction (Motivation / Novelty and Contributions / Paper Organization), 2 Related Work,
3 Methodology (Research Questions first), 4 Data, 5 Results, 6 Discussion, 7 Limitations and Future Work,
8 Conclusion, numbered references, appendices.

Every number in Sections 4-5 and in the abstract is read from the pipeline outputs, so the text always
matches the tables. Prose markup: {cite:a,b} numbered citation; {ref:label} cross-reference; {m:x} math.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

HERE = Path(__file__).resolve().parent
MODEL = HERE / "model"
sys.path.insert(0, str(MODEL))
from common import (CF_COLS, DEMO_STAMP as STAMP, POLICIES, SPIKE_THRESHOLD, UNCERTAINTIES,  # noqa: E402
                    compute_outcomes, counterfactual_params, model_time_step, run)

OUT = Path(sys.argv[sys.argv.index("--outputs") + 1]) if "--outputs" in sys.argv else MODEL / "outputs"
TEX_DIR = HERE / "latex"
FIG_DIR = TEX_DIR / "figures"
PDF_DST = HERE / "MBG_paper.pdf"
DT = model_time_step()

# ------------------------------------------------------------------ author
AUTHOR = "Daniel Amazing Silalahi"
AFFILIATION = ("Department of Mechanical and Industrial Engineering, Faculty of Engineering, "
               "Universitas Gadjah Mada, Yogyakarta, Indonesia")
EMAIL = "danielamazingsilalahi2004@mail.ugm.ac.id"
TITLE = ("Programme-Driven Demand Shocks in Food Supply Chains: System Dynamics and Machine-Learning "
         "Scenario Discovery for Indonesia's Free Nutritious Meals Programme")
KEYWORDS = ("system dynamics; scenario discovery; machine learning; food supply chain; demand shock; "
            "school meals programme; public procurement; Indonesia")

# ------------------------------------------------------------------ references (IEEE style, order of first citation)
REFS = {
    "bgn2025": r"Badan Gizi Nasional, ``Awal Januari 2026, BGN operasikan 19.188 SPPG,'' press release, Jan. 2026. "
               r"[Online]. Available: https://www.bgn.go.id/news/siaran-pers/awal-januari-2026-bgn-operasikan-19188-sppg",
    "antara2026": r"Antara, ``BGN: 21.897 SPPG sudah beroperasi layani 65 juta penerima manfaat MBG,'' 12 Feb. 2026. "
                  r"[Online]. Available: https://www.antaranews.com/berita/5414198",
    "budget": r"Kontan, ``Prabowo naikkan anggaran MBG 94,76\% di 2026, tembus Rp 335 triliun,'' Aug. 2025. [Online]. "
              r"Available: https://nasional.kontan.co.id/news/prabowo-naikkan-anggaran-mbg-9476-di-2026-tembus-rp-335-triliun",
    "meadows1970": r"D. L. Meadows, \textit{Dynamics of Commodity Production Cycles}. Cambridge, MA: Wright-Allen Press, 1970.",
    "sterman2000": r"J. D. Sterman, \textit{Business Dynamics: Systems Thinking and Modeling for a Complex World}. "
                   r"Boston, MA: Irwin/McGraw-Hill, 2000.",
    "bps2025": r"Bisnis.com, ``BPS duga program MBG jadi pemicu inflasi telur dan daging ayam,'' 3 Nov. 2025. [Online]. "
               r"Available: https://ekonomi.bisnis.com/read/20251103/9/1925640",
    "kementan2025": r"Bisnis.com, ``Kementan pastikan harga telur dan ayam stabil, pasokan untuk program MBG aman,'' "
                    r"19 Nov. 2025. [Online]. Available: https://ekonomi.bisnis.com/read/20251119/12/1930149",
    "prabowo2025": r"Republika, ``Prabowo minta sementara telur ayam di menu MBG diganti telur puyuh,'' 21 Nov. 2025. "
                   r"[Online]. Available: https://news.republika.co.id/berita/t61xeu409",
    "egg3x2026": r"Detik Finance, ``Menu telur program MBG minimal 3 kali seminggu imbas harga anjlok,'' June 2026. "
                 r"[Online]. Available: https://finance.detik.com/berita-ekonomi-bisnis/d-8522633",
    "holiday2026": r"CNN Indonesia, ``MBG bumil, busui dan balita ikut disetop sementara saat libur sekolah,'' "
                   r"19 June 2026. [Online]. Available: https://www.cnnindonesia.com/ekonomi/20260619124748-92-1370802",
    "amran2026": r"CNN Indonesia, ``MBG libur, Amran minta perusahaan serap telur-daging ayam peternak,'' 17 June 2026. "
                 r"[Online]. Available: https://www.cnnindonesia.com/ekonomi/20260617180357-92-1370127",
    "okezone2026": r"Okezone, ``Harga ayam dan telur naik, Mentan sebut efek MBG,'' 27 July 2026. [Online]. Available: "
                   r"https://economy.okezone.com/read/2026/07/27/320/3232582",
    "handbury2021": r"J. Handbury and S. Moshary, ``School food policy affects everyone: Retail responses to the "
                    r"National School Lunch Program,'' NBER Working Paper 29384, 2021. https://doi.org/10.3386/w29384",
    "gelli2021": r"A. Gelli, E. Masset, \textit{et al.}, ``School meals as a market for smallholder agriculture: "
                 r"Experimental evidence from Ghana,'' IFPRI Discussion Paper 02045, International Food Policy Research "
                 r"Institute, Washington, DC, 2021.",
    "ipb2026": r"``Analisis struktur rantai pasok pangan dan keterlibatan UMKM lokal dalam pelaksanaan program Makan "
               r"Bergizi Gratis (MBG) di Kota Tangerang Selatan,'' \textit{Jurnal Manajemen dan Organisasi}, vol. 17, "
               r"no. 3, pp. 275--291, 2026. https://doi.org/10.29244/jmo.v17i3.73792",
    "ambarwati2025": r"O. C. Ambarwati and H. Kurniawati, ``Strategi pemanfaatan potensi pangan lokal untuk mendukung "
                     r"program Makan Bergizi Gratis di Jawa Tengah,'' \textit{Analisis Kebijakan Pembangunan}, vol. 2, "
                     r"no. 1, pp. 47--60, 2025.",
    "mitchell2024": r"J. L. Mitchell, J. M. Thompson, and T. Malone, ``Biological lags and market dynamics in vertically "
                    r"coordinated food supply chains: HPAI impacts on U.S. egg prices,'' \textit{Food Policy}, vol. 126, "
                    r"102655, 2024. https://doi.org/10.1016/j.foodpol.2024.102655",
    "haryana2026": r"A. Haryana, Suprayogi, R. Wangsaputra, and R. Govindaraju, ``Regional food supply system planning: "
                   r"A system dynamics analysis of broiler chicken supply and price stabilization policies in Indonesia,'' "
                   r"\textit{Journal of Regional and City Planning}, vol. 37, no. 1, pp. 52--96, 2026. "
                   r"https://doi.org/10.5614/jpwk.2026.37.1.3",
    "aboah2022": r"J. Aboah and D. Enahoro, ``A systems thinking approach to understand the drivers of change in "
                 r"backyard poultry farming system,'' \textit{Agricultural Systems}, vol. 202, 103475, 2022. "
                 r"https://doi.org/10.1016/j.agsy.2022.103475",
    "friedman1999": r"J. H. Friedman and N. I. Fisher, ``Bump hunting in high-dimensional data,'' "
                    r"\textit{Statistics and Computing}, vol. 9, no. 2, pp. 123--143, 1999. "
                    r"https://doi.org/10.1023/A:1008894516817",
    "bryant2010": r"B. P. Bryant and R. J. Lempert, ``Thinking inside the box: A participatory, computer-assisted "
                  r"approach to scenario discovery,'' \textit{Technological Forecasting and Social Change}, vol. 77, "
                  r"no. 1, pp. 34--49, 2010. https://doi.org/10.1016/j.techfore.2009.08.002",
    "kwakkel2016": r"J. H. Kwakkel and M. Jaxa-Rozen, ``Improving scenario discovery for handling heterogeneous "
                   r"uncertainties and multinomial classified outcomes,'' \textit{Environmental Modelling \& "
                   r"Software}, vol. 79, pp. 311--321, 2016. https://doi.org/10.1016/j.envsoft.2015.11.020",
    "kwakkel2017": r"J. H. Kwakkel, ``The Exploratory Modeling Workbench: An open source toolkit for exploratory "
                   r"modeling, scenario discovery, and (multi-objective) robust decision making,'' "
                   r"\textit{Environmental Modelling \& Software}, vol. 96, pp. 239--250, 2017. "
                   r"https://doi.org/10.1016/j.envsoft.2017.06.054",
    "steinmann2020": r"P. Steinmann, W. L. Auping, and J. H. Kwakkel, ``Behavior-based scenario discovery using "
                     r"time series clustering,'' \textit{Technological Forecasting and Social Change}, vol. 156, "
                     r"120052, 2020. https://doi.org/10.1016/j.techfore.2020.120052",
    "lundberg2017": r"S. M. Lundberg and S.-I. Lee, ``A unified approach to interpreting model predictions,'' in "
                    r"\textit{Advances in Neural Information Processing Systems}, vol. 30, 2017.",
    "breiman2001": r"L. Breiman, ``Random forests,'' \textit{Machine Learning}, vol. 45, no. 1, pp. 5--32, 2001. "
                   r"https://doi.org/10.1023/A:1010933404324",
    "barlas1996": r"Y. Barlas, ``Formal aspects of model validity and validation in system dynamics,'' "
                  r"\textit{System Dynamics Review}, vol. 12, no. 3, pp. 183--210, 1996.",
    "pysd": r"J. Houghton and M. Siegel, ``Advanced data analytics for system dynamics models using PySD,'' in "
            r"\textit{Proc. 33rd Int. System Dynamics Conf.}, Cambridge, MA, 2015.",
    "sterman1984": r"J. D. Sterman, ``Appropriate summary statistics for evaluating the historical fit of system "
                   r"dynamics models,'' \textit{Dynamica}, vol. 10, no. 2, pp. 51--66, 1984.",
    "mckay1979": r"M. D. McKay, R. J. Beckman, and W. J. Conover, ``A comparison of three methods for selecting "
                 r"values of input variables in the analysis of output from a computer code,'' "
                 r"\textit{Technometrics}, vol. 21, no. 2, pp. 239--245, 1979. https://doi.org/10.1080/00401706.1979.10489755",
    "wilson1927": r"E. B. Wilson, ``Probable inference, the law of succession, and statistical inference,'' "
                  r"\textit{Journal of the American Statistical Association}, vol. 22, no. 158, pp. 209--212, 1927. "
                  r"https://doi.org/10.1080/01621459.1927.10502953",
    "wilcoxon1945": r"F. Wilcoxon, ``Individual comparisons by ranking methods,'' \textit{Biometrics Bulletin}, "
                    r"vol. 1, no. 6, pp. 80--83, 1945. https://doi.org/10.2307/3001968",
    "holm1979": r"S. Holm, ``A simple sequentially rejective multiple test procedure,'' \textit{Scandinavian "
                r"Journal of Statistics}, vol. 6, no. 2, pp. 65--70, 1979.",
    "kerby2014": r"D. S. Kerby, ``The simple difference formula: An approach to teaching nonparametric "
                 r"correlation,'' \textit{Comprehensive Psychology}, vol. 3, 2014. https://doi.org/10.2466/11.IT.3.1",
    "mcnemar1947": r"Q. McNemar, ``Note on the sampling error of the difference between correlated proportions or "
                   r"percentages,'' \textit{Psychometrika}, vol. 12, no. 2, pp. 153--157, 1947. "
                   r"https://doi.org/10.1007/BF02295996",
    "friedman1937": r"M. Friedman, ``The use of ranks to avoid the assumption of normality implicit in the analysis "
                    r"of variance,'' \textit{Journal of the American Statistical Association}, vol. 32, no. 200, "
                    r"pp. 675--701, 1937. https://doi.org/10.1080/01621459.1937.10503522",
    "wfp": r"World Food Programme, ``Indonesia -- Food Prices,'' Humanitarian Data Exchange, licence CC BY-IGO. "
           r"[Online]. Available: https://data.humdata.org/dataset/72cc0659-142b-41af-821a-cb981a852617 "
           r"(accessed 7 Nov. 2026).",
    "neweywest1987": r"W. K. Newey and K. D. West, ``A simple, positive semi-definite, heteroskedasticity and "
                     r"autocorrelation consistent covariance matrix,'' \textit{Econometrica}, vol. 55, no. 3, "
                     r"pp. 703--708, 1987. https://doi.org/10.2307/1913610",
    "sppgpress": r"Press reports of BGN statements on operational SPPG, 2025--2026: Bisnis.com (24 June and "
                 r"28 Sep. 2025), Investortrust (8 Sep. 2025), CNN Indonesia (16 Sep. 2025), Kompas TV (18 June 2026) "
                 r"and Kementerian Keuangan via RM.id (Oct. 2026). Full list with URLs in the data repository.",
    "bgnaug2025": r"Badan Gizi Nasional, ``Program MBG sentuh 15 juta penerima manfaat, BGN bidik 82,9 juta pada akhir "
                  r"2025,'' press release, Aug. 2025. [Online]. Available: https://www.bgn.go.id/news/siaran-pers/"
                  r"program-mbg-sentuh-15-juta-penerima-manfaat-bgn-bidik-829-juta-pada-akhir-2025",
    "bpsprod": r"Badan Pusat Statistik, ``Produksi Telur Ayam Petelur menurut Provinsi (Ton), 2024'' and "
               r"``Produksi Daging Ayam Ras Pedaging menurut Provinsi (Ton), 2024,'' preliminary figures, Jakarta, 2025.",
    "khoiriyah2024": r"N. Khoiriyah, D. Forgenie, S. Sookhai, and A. J. Saputro, ``Demand elasticities of "
                     r"animal-sourced food: Empirical study in Yogyakarta, Indonesia,'' \textit{International "
                     r"Journal of Food and Agricultural Economics}, vol. 12, no. 3, pp. 171--188, 2024.",
    "bgnegg2025": r"Bisnis.com, ``Kepala BGN wanti-wanti RI bisa krisis telur buat penuhi MBG,'' 8 Apr. 2025. "
                  r"[Online]. Available: https://ekonomi.bisnis.com/read/20250408/12/1867518",
    "cap2025": r"Detik Finance, ``BGN batasi dapur MBG maksimal siapkan 3.000 porsi per hari,'' Oct. 2025. [Online]. "
               r"Available: https://finance.detik.com/berita-ekonomi-bisnis/d-8185320",
    "gopan2025": r"Kontan, ``Produksi ditambah, GOPAN: pasokan ayam masih lebih untuk program MBG,'' Nov. 2025. "
                 r"[Online]. Available: https://industri.kontan.co.id/news/produksi-ditambah-gopan-pasokan-ayam-masih-"
                 r"lebih-untuk-program-mbg",
    "lohmann": r"Lohmann Breeders, \textit{Lohmann Brown-Classic Layers: Management Guide}. Cuxhaven, Germany: "
               r"Lohmann Breeders GmbH.",
}
CITED: list[str] = []

# ------------------------------------------------------------------ helpers
_ESC = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
        "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
        "<": r"\textless{}", ">": r"\textgreater{}"}


def esc(s) -> str:
    return "".join(_ESC.get(c, c) for c in str(s))


def T(s: str) -> str:
    out = []
    for tok in re.split(r"(\{cite:[^}]*\}|\{ref:[^}]*\}|\{m:[^}]*\})", s):
        if tok.startswith("{cite:"):
            keys = [k.strip() for k in tok[6:-1].split(",")]
            for k in keys:
                if k not in REFS:
                    raise KeyError(f"unknown reference key {k}")
                if k not in CITED:
                    CITED.append(k)
            out.append(r"~\cite{" + ",".join(keys) + "}")
        elif tok.startswith("{ref:"):
            out.append(r"\ref{" + tok[5:-1] + "}")
        elif tok.startswith("{m:"):
            out.append("$" + tok[3:-1] + "$")
        else:
            out.append(esc(tok))
    return "".join(out)


B: list[str] = []


def _lab(label): return rf"\label{{{label}}}" if label else ""
def sec(t, label=None): B.append(rf"\section{{{T(t)}}}" + _lab(label))
def sub(t, label=None): B.append(rf"\subsection{{{T(t)}}}" + _lab(label))
def par(t): B.append(T(t) + "\n")
def raw(s): return "RAW:" + s


def items(lst, enum=False):
    env = "enumerate" if enum else "itemize"
    B.append(rf"\begin{{{env}}}" + "".join(rf"\item {T(x)} " for x in lst) + rf"\end{{{env}}}")


def num(v, fmt=3):
    if isinstance(v, (bool, np.bool_)):
        return "Yes" if v else "No"
    if isinstance(v, (int, np.integer)):
        return f"{v:,}"
    if isinstance(v, float):
        return "--" if pd.isna(v) else (f"{v:,.0f}" if abs(v) >= 1e5 else f"{v:,.{fmt}f}")
    return T(str(v))


def pval(p): return "$<$0.001" if p < 0.001 else f"{p:.3f}"


def table(rows, header, caption, colspec, wide=False, size=r"\footnotesize", fmt=3, label=None):
    env = "table*" if wide else "table"
    tab = "tabularx" if "X" in colspec else "tabular"
    width = r"{\linewidth}" if tab == "tabularx" else ""
    L = [rf"\begin{{{env}}}[{'!t' if wide else '!htb'}]", r"\centering", size,
         rf"\caption{{{T(caption)}}}" + _lab(label), rf"\begin{{{tab}}}{width}{{{colspec}}}", r"\toprule",
         " & ".join(rf"\textbf{{{T(h)}}}" for h in header) + r" \\", r"\midrule"]
    for r in rows:
        L.append(" & ".join(c[4:] if isinstance(c, str) and c.startswith("RAW:") else num(c, fmt) for c in r) + r" \\")
    L += [r"\bottomrule", rf"\end{{{tab}}}", rf"\end{{{env}}}"]
    B.append("\n".join(L))


def figure(name, caption, wide=False, label=None):
    f = OUT / name
    if not f.exists():
        raise FileNotFoundError(f)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy(f, FIG_DIR / name)
    env = "figure*" if wide else "figure"
    w = r"\textwidth" if wide else r"\linewidth"
    B.append("\n".join([rf"\begin{{{env}}}[{'!t' if wide else '!htb'}]", r"\centering",
                        rf"\includegraphics[width={w}]{{figures/{name}}}",
                        rf"\caption{{{T(caption)}}}" + _lab(label), rf"\end{{{env}}}"]))


def tikz_figure(code, caption, label, wide=False):
    env = "figure*" if wide else "figure"
    B.append("\n".join([rf"\begin{{{env}}}[{'!t' if wide else '!htb'}]", r"\centering", code,
                        rf"\caption{{{T(caption)}}}" + _lab(label), rf"\end{{{env}}}"]))


def verbatim(text, caption, label=None):
    B.append("\n".join([r"\begin{figure}[!htb]", r"\centering", rf"\caption{{{T(caption)}}}" + _lab(label),
                        r"\begin{minipage}{\linewidth}\scriptsize", r"\begin{verbatim}", text.rstrip(),
                        r"\end{verbatim}", r"\end{minipage}", r"\end{figure}"]))


def read(name, **kw):
    return pd.read_csv(OUT / name, comment="#", **kw)


def pct(x, d=1): return f"{100 * x:.{d}f}%"
def pp(x, d=1): return f"{100 * x:.{d}f}"


SHORT = {"P0 Baseline": "P0", "P1 Phased roll-out": "P1", "P2 Cooperative sourcing": "P2",
         "P3 Forward contracts": "P3", "P4 Menu flexibility": "P4", "P5 Combined (P2+P3+P4)": "P5"}
LABEL = {"P0 Baseline": "The baseline", "P1 Phased roll-out": "Phasing the roll-out",
         "P2 Cooperative sourcing": "Cooperative sourcing", "P3 Forward contracts": "Forward contracting",
         "P4 Menu flexibility": "Menu flexibility", "P5 Combined (P2+P3+P4)": "The combined policy"}

# ================================================================== FACTS FROM OUTPUTS
val = read("validation_tests.csv", index_col=0)
a_tests = val[val.index.str.startswith("A")]
b1 = val[val.index.str.startswith("B1")].iloc[0]
b2 = val[val.index.str.startswith("B2")].iloc[0]
rec = read("parameter_recovery_test.csv", index_col=0)
cal = pd.read_csv(MODEL / "data" / "calibrated_parameters.csv", index_col=0)
beh = read("behaviour_reproduction.csv", index_col=0)
EGG, CHK = beh.loc["egg (seasonally adjusted)"], beh.loc["chicken (seasonally adjusted)"]
seas = read("seasonal_regression.csv")
sr = lambda s, t: seas[(seas.series == s) & (seas.term == t)].iloc[0]
roll = pd.read_csv(MODEL / "data" / "rollout_fit.csv")
ens = pd.read_csv(OUT / "ensemble_results.csv", usecols=["scenario"])
N_SCEN = int(ens["scenario"].nunique())
ps = read("policy_summary.csv", index_col=0)
P0 = ps.loc["P0 Baseline"]
mc = read("policy_mcnemar_spike.csv", index_col=0)
wx = read("policy_wilcoxon_vs_P0.csv")
fr = read("policy_friedman.csv", index_col=0)
cb = read("sd_classifier_benchmark.csv", index_col=0)
best_clf = cb["roc_auc_mean"].idxmax()
shap = read("sd_shap_importance.csv", index_col=0)["mean_abs_shap"].sort_values(ascending=False)
oat = read("sd_oat_sensitivity.csv", index_col=0)
RHO = float(spearmanr(oat["swing"].reindex(shap.index), shap.values).statistic)
oat_top = oat["swing"].sort_values(ascending=False)
traj = read("sd_prim_trajectory.csv", index_col=0)
ok = traj[traj["density"] >= 0.8]
BOX = traj.loc[int(ok["coverage"].idxmax()) if len(ok) else int(traj["density"].idxmax())]
prim = read("sd_prim_box.csv", index_col=0)
prim_m = prim[prim["meaningful"].astype(str) == "True"]
ew = read("ew_classifier_benchmark.csv", index_col=0)
ew_rules = (OUT / "ew_rules.txt").read_text()
cart_rules = (OUT / "sd_cart_rules.txt").read_text()
tsr = read("time_step_robustness_summary.csv", index_col=0)["value"]
VEQ = read("vector_equivalence.csv", index_col=0)["value"]

# baseline with and without the programme (same calibrated model as the ensemble)
_base = run()
_cf = run(counterfactual_params({}), columns=CF_COLS)
BASE = compute_outcomes(_base, _cf)
_ex_egg = (_base["Relative egg price"] - _cf["Relative egg price"])[_base.index >= 53]
_ex_chk = (_base["Relative chicken price"] - _cf["Relative chicken price"])[_base.index >= 53]
WEEK0 = pd.Timestamp("2024-01-01")
wdate = lambda w: (WEEK0 + pd.Timedelta(weeks=float(w))).strftime("%B %Y")


def nice(name):
    return name[0].lower() + name[1:] if not name.startswith(("MBG", "DOC")) else name


PNAME = {"Chicken per beneficiary": "chicken quantity per beneficiary",
         "Future beneficiaries per kitchen": "future number of beneficiaries per kitchen",
         "Egg serving size": "egg serving size", "Egg servings after menu change": "egg servings per week after June 2026",
         "Target kitchens": "final number of kitchens", "Outbreak loss fraction": "size of a disease outbreak",
         "Feed shock magnitude": "size of the feed-price shock",
         "Household egg elasticity": "household egg price elasticity",
         "Household chicken elasticity": "household chicken price elasticity",
         "Price sensitivity to coverage": "sensitivity of price to inventory coverage"}
pn = lambda k: PNAME.get(k, nice(k))
spike = {k: ps.loc[k, "spike_prob"] for k in ps.index}

# ================================================================== ABSTRACT
best_pol = min((k for k in ps.index if k != "P0 Baseline"), key=lambda k: spike[k])
single = [k for k in ps.index if k not in ("P0 Baseline", "P5 Combined (P2+P3+P4)")]
best_single = min(single, key=lambda k: spike[k])
ABSTRACT = (
    "Indonesia's Free Nutritious Meals programme (Makan Bergizi Gratis, MBG) has created a large, fast-growing and "
    "price-inelastic public demand for eggs and broiler meat, and whether it drives food price increases is "
    "disputed between government agencies. This paper develops a system dynamics model of the egg and broiler "
    "supply chains under MBG that represents kitchen roll-out and suspensions, menu and school-holiday rules, "
    "biological production delays, farmer investment and price formation. The model is calibrated to national "
    "retail prices and programme statistics and validated with structural and behavioural tests. It is run as an "
    f"exploratory ensemble of {N_SCEN:,} scenarios, each simulated with and without the programme so that "
    "programme-attributable price effects are separated from seasonal and external shocks, and machine-learning "
    "scenario discovery (classifiers, SHAP and PRIM) is used to identify the conditions that produce price spikes. "
    f"Under current policy, the programme raises egg or chicken prices by more than {pp(SPIKE_THRESHOLD, 0)} "
    f"percentage points in {pct(P0['spike_prob'])} of scenarios. Spike risk is driven mainly by "
    f"{pn(shap.index[0])} and {pn(shap.index[1])}" + (
        f", and a one-at-a-time sensitivity analysis ranks the drivers differently (Spearman {{m:\\rho}} = "
        f"{RHO:.2f}), missing interactions that scenario discovery reveals. " if RHO < 0.7 else ". ") +
    f"{LABEL[best_single]} ({SHORT[best_single]}) is the most effective single policy, lowering spike probability to "
    f"{pct(spike[best_single])}, and combining cooperative sourcing, forward contracts and menu flexibility lowers "
    f"it to {pct(spike['P5 Combined (P2+P3+P4)'])}" + (
        " while reducing protein cost per portion. " if ps.loc["P5 Combined (P2+P3+P4)", "mean_cost_per_portion_median"]
        < P0["mean_cost_per_portion_median"] else ". ") + (
        f"Price spikes are hard to anticipate from indicators observable early in the roll-out (ROC AUC "
        f"{ew['roc_auc_mean'].max():.2f}), which favours designing procurement in advance over reacting to prices."
        if ew["roc_auc_mean"].max() < 0.85 else
        f"Indicators observable early in the roll-out anticipate spikes well (ROC AUC {ew['roc_auc_mean'].max():.2f})."))

# ================================================================== 1 INTRODUCTION
sec("Introduction", "sec:intro")
sub("Motivation")
par("Large public food programmes do more than feed their beneficiaries: they also change the markets they buy "
    "from. Indonesia's Free Nutritious Meals programme (Makan Bergizi Gratis, MBG), launched on 6 January 2025, is "
    "one of the largest public food procurement programmes in the world. By the end of 2025 the National Nutrition "
    "Agency (Badan Gizi Nasional, BGN) operated 19,188 meal-preparation units (Satuan Pelayanan Pemenuhan Gizi, "
    "SPPG) serving 55.1 million beneficiaries {cite:bgn2025}, rising to 21,897 units and 65 million beneficiaries "
    "by February 2026 {cite:antara2026}. The programme budget rose from Rp 171 trillion in 2025 to a proposed "
    "Rp 335 trillion in 2026 {cite:budget}.")
par("Eggs and broiler meat are core protein items on MBG menus. Unlike household demand, programme demand is set "
    "by menus, kitchen numbers and the school calendar rather than by price, and it grows as fast as new kitchens "
    "open. Supply adjusts slowly: pullets take about 18 weeks to reach point of lay, and farmers expand flocks on "
    "the basis of expected prices and margins. A fast, price-inelastic increase in demand meeting a slow, "
    "biologically delayed supply response is a classic setting for price overshoot and commodity cycles "
    "{cite:meadows1970,sterman2000}.")
par("The first two years of the programme show this tension, and its interpretation is contested. Statistics "
    "Indonesia (BPS) attributed part of the October 2025 inflation in eggs and chicken meat to demand from MBG "
    "kitchens {cite:bps2025}, whereas the Ministry of Agriculture described prices as stable and supply as "
    "sufficient {cite:kementan2025}. In November 2025 the President asked kitchens to replace chicken eggs "
    "temporarily with other proteins as prices rose {cite:prabowo2025}. In June 2026, when farm-gate egg prices "
    "fell below the government reference price, BGN and farmer groups agreed to serve eggs at least three times a "
    "week {cite:egg3x2026}; when meals paused for the school holiday the Minister of Agriculture asked companies to "
    "absorb farmers' eggs and chicken {cite:amran2026}, and when schools reopened he attributed the following price "
    "rise to MBG demand {cite:okezone2026}. Menus, serving days and holiday rules have therefore become de facto "
    "market-stabilisation instruments, adjusted reactively.")
par("These events raise questions that statistical analysis of short price series cannot settle: how much of the "
    "price movement is caused by the programme rather than by seasonal or external shocks; under which conditions "
    "programme demand produces a severe price spike; and which policies, from the speed of roll-out and the "
    "sourcing structure to advance contracting with farmers and flexible menus, reduce that risk. Answering them "
    "requires a model that captures feedback and delays across the supply chain, and an analysis that explores many "
    "plausible futures rather than a single forecast.")
sub("Novelty and Contributions")
items([
    "A system dynamics model of Indonesia's egg and broiler supply chains under a national school-meals programme, "
    "calibrated to public price and programme data and including the programme's menu and school-holiday rules, "
    "with a counterfactual design that separates programme effects from seasonal and external shocks (Sections "
    "{ref:sec:method} and {ref:sec:data}).",
    "A combination of system dynamics and machine-learning scenario discovery (a classifier benchmark, SHAP and "
    "PRIM) that yields interpretable spike conditions, compared with one-at-a-time sensitivity analysis (Section "
    "{ref:sec:spikes}).",
    "An early-warning analysis testing whether indicators observable 13 weeks after programme launch predict later "
    "price spikes (Section {ref:sec:ew}).",
    f"A paired statistical comparison of roll-out and procurement policies on {N_SCEN:,} common scenarios "
    "(Section {ref:sec:policy})."], enum=True)
sub("Paper Organization")
par("Section {ref:sec:related} reviews related work. Section {ref:sec:method} describes the research questions, "
    "model and analysis, and Section {ref:sec:data} the data. Section {ref:sec:results} presents the results, "
    "Section {ref:sec:discussion} discusses them, Section {ref:sec:limits} states limitations and directions for "
    "future work, and Section {ref:sec:conclusion} concludes.")

# ================================================================== 2 RELATED WORK
sec("Related Work", "sec:related")
sub("Public Food Procurement and School Meals")
par("School meals programmes are usually evaluated for their effects on children's nutrition and learning, but "
    "large programmes also act on food markets. Handbury and Moshary {cite:handbury2021} show that the United "
    "States National School Lunch Program affects retail food markets beyond the children it serves, so that a "
    "public meals programme has consequences for households that do not participate in it. Home-grown school "
    "feeding links meals to local smallholder procurement in the expectation of raising farm demand and incomes; "
    "a cluster-randomised evaluation in Ghana, however, found no strong evidence that the programme changed local "
    "market structure or farm incomes, and argued that effects depend on whether local markets are integrated with "
    "wider markets and on the scale of procurement {cite:gelli2021}.")
par("Research on MBG is recent and mainly descriptive. A study of Tangerang Selatan maps the programme's food "
    "supply chain from ingredient sources through procurement channels and kitchens to beneficiaries, and finds "
    "that local small enterprises take part largely through partners and cooperatives acting as procurement "
    "channels {cite:ipb2026}. In Central Java, sourcing from local producers had not been achieved because of "
    "constraints in quality, quantity, continuity and price, and supply still relied on inter-regional market "
    "mechanisms rather than local contracts {cite:ambarwati2025}. These studies describe procurement structures "
    "but do not quantify how programme demand moves prices over time.")
sub("Demand Shocks, Biological Lags and Commodity Cycles")
par("Livestock markets are prone to cycles because production capacity responds to prices only after a "
    "biological delay. Meadows {cite:meadows1970} showed that commodity production cycles arise endogenously when "
    "producers invest on the basis of current prices and ignore capacity already in the pipeline, a mechanism "
    "generalised by Sterman {cite:sterman2000} as supply-line underestimation. Mitchell, Thompson and Malone "
    "{cite:mitchell2024} show the empirical importance of such lags for eggs: highly pathogenic avian influenza "
    "raised weekly United States retail egg prices by 5.3% on average, and models that ignore the time needed to "
    "replace a depopulated flock underestimate the impact. The shocks studied in this literature are disease, "
    "feed and seasonal shocks, not demand shocks created by public programmes.")
sub("System Dynamics in Poultry Supply Chains")
par("System dynamics has been used to explain poultry market behaviour. Haryana et al. {cite:haryana2026} build "
    "a model of Indonesia's broiler supply system, linking grandparent and parent stock, day-old-chick allocation, "
    "integrator and independent grow-out, slaughter and cold storage, and show that recurring live-bird price "
    "instability arises from the structure of the system; they conclude that stabilisation requires coordinated "
    "management of breeding capacity, hatchery operations and downstream buffering. Aboah and Enahoro "
    "{cite:aboah2022} model backyard poultry farming in Ghana over a 52-week horizon and show that the drivers of "
    "the system change within the year. Neither study considers a public programme as a source of demand, and both "
    "analyse a small number of scenarios.")
sub("Scenario Discovery and Machine Learning on Simulation Models")
par("Scenario discovery applies statistical learning to large ensembles of simulation runs to find the "
    "combinations of uncertain inputs that lead to outcomes of interest {cite:bryant2010}. The Patient Rule "
    "Induction Method (PRIM) {cite:friedman1999} finds a box in the input space with a high share of such outcomes "
    "and reports the trade-off between coverage and density; later work extended the approach to heterogeneous "
    "uncertainties {cite:kwakkel2016} and to behaviour patterns over time {cite:steinmann2020}, and the EMA "
    "Workbench made it widely available {cite:kwakkel2017}. Tree ensembles such as random forests "
    "{cite:breiman2001} combined with SHAP values {cite:lundberg2017} offer a complementary, model-agnostic way to "
    "rank and interpret drivers. These methods have been applied mainly to energy, water and climate policy, and "
    "rarely to food supply chains or to public programmes in developing economies.")
sub("Research Gap")
par("Table {ref:tab:gap} positions this study. Existing work either measures market effects of meals programmes "
    "without modelling supply dynamics, or models poultry supply dynamics without programme demand, and none uses "
    "scenario discovery. This study combines the three.")
table([["Handbury & Moshary {cite:handbury2021}", "USA, school lunch", "Econometric", "Yes", "No", "No"],
       ["Gelli et al. {cite:gelli2021}", "Ghana, school feeding", "Randomised trial", "Yes", "No", "No"],
       ["IPB study {cite:ipb2026}; Ambarwati & Kurniawati {cite:ambarwati2025}", "Indonesia, MBG",
        "Descriptive", "Yes", "No", "No"],
       ["Mitchell et al. {cite:mitchell2024}", "USA, eggs, avian influenza", "Econometric with lags", "No",
        "Partly", "No"],
       ["Haryana et al. {cite:haryana2026}", "Indonesia, broilers", "System dynamics", "No", "Yes", "No"],
       ["Aboah & Enahoro {cite:aboah2022}", "Ghana, backyard poultry", "System dynamics", "No", "Yes", "No"],
       ["Bryant & Lempert {cite:bryant2010}; Kwakkel {cite:kwakkel2017}", "Methods", "Scenario discovery", "No",
        "--", "Yes"],
       ["This study", "Indonesia, MBG, eggs and broilers", "SD + ML scenario discovery", "Yes", "Yes", "Yes"]],
      ["Study", "Context", "Method", "Programme demand", "Dynamic feedback", "Scenario discovery"],
      "Positioning of this study relative to prior work",
      r">{\raggedright\arraybackslash}X>{\raggedright\arraybackslash}p{3.2cm}>{\raggedright\arraybackslash}p{3cm}ccc",
      wide=True, size=r"\scriptsize", label="tab:gap")

# ================================================================== 3 METHODOLOGY
sec("Methodology", "sec:method")
sub("Research Questions")
B.append(r"\noindent\textbf{RQ1:} " + T("How does the MBG roll-out propagate through Indonesia's egg and broiler "
                                        "supply chains to market prices and household consumption over time?") +
         r" \textbf{RQ2:} " + T("Under which combinations of uncertain conditions does the programme cause severe "
                                "programme-attributable price spikes?") +
         r" \textbf{RQ3:} " + T("Which roll-out and procurement policies reduce spike risk while maintaining "
                                "programme coverage and cost?") + "\n")
sub("Research Design")
par("The study combines system dynamics (SD) simulation with machine-learning scenario discovery (Figure "
    "{ref:fig:framework}). An SD model of the egg and broiler supply chains under MBG was built in Vensim, "
    "calibrated to public data and validated with structural and behavioural tests {cite:barlas1996}. It was then "
    "run as an exploratory ensemble over uncertain parameters and alternative policies using PySD {cite:pysd}. "
    "Classifiers, SHAP values {cite:lundberg2017} and PRIM {cite:friedman1999,bryant2010}, implemented with the EMA "
    "Workbench {cite:kwakkel2017}, were used to identify the conditions under which the programme produces severe "
    "price increases, and policies were compared on a common set of scenarios with paired non-parametric tests.")
TIKZ_FRAMEWORK = r"""
\begin{tikzpicture}[node distance=2.6mm, box/.style={draw, rounded corners=2pt, align=center, font=\scriptsize,
  text width=0.9\linewidth, inner sep=2.5pt, fill=gray!8}, arr/.style={-{Stealth[length=1.6mm]}, semithick}]
\node[box] (d) {\textbf{Data}: WFP retail prices 2007--2026; BGN kitchens, beneficiaries and suspensions;
 BPS production; SUSENAS elasticities; menu and school-holiday rules};
\node[box, below=of d] (m) {\textbf{System dynamics model (Vensim)}: programme, layer, broiler and market sectors};
\node[box, below=of m] (c) {\textbf{Calibration and validation}: seasonal adjustment; roll-out and suspension fit;
 extreme-condition, integration-error, parameter-recovery and behaviour-reproduction tests};
\node[box, below=of c] (e) {\textbf{Exploratory ensemble}: """ + f"{N_SCEN:,}" + r""" Latin Hypercube scenarios
 $\times$ 6 policies, each with a no-programme counterfactual \hfill (RQ1)};
\node[box, below=of e] (s) {\textbf{Scenario discovery and early warning}: classifier benchmark, SHAP, PRIM,
 one-at-a-time comparison, early-warning classifier \hfill (RQ2)};
\node[box, below=of s] (p) {\textbf{Policy comparison}: Wilson intervals, Wilcoxon signed-rank (Holm), McNemar,
 Friedman \hfill (RQ3)};
\foreach \a/\b in {d/m, m/c, c/e, e/s, s/p} \draw[arr] (\a) -- (\b);
\end{tikzpicture}"""
tikz_figure(TIKZ_FRAMEWORK, "Research framework", "fig:framework")
sub("Model Structure")
par("The model has four interacting sectors simulated weekly from January 2024 to December 2029 (312 weeks, "
    f"Euler integration with a time step of {DT:g} week). The step is one-sixteenth of the shortest time constant, "
    "the half-week minimum delivery time that limits sales when demand jumps as schools reopen, and school-holiday "
    "dates are rounded to the nearest 1/16 week so that both time steps in the integration tests switch meals on "
    "and off at the same moments. Figure {ref:fig:cld} shows the main feedback loops, Figure {ref:fig:sfd} the "
    "stock-and-flow structure, and Appendix {ref:app:eq} lists all equations.")
for head, txt in [
    ("Programme sector.", "Planned kitchens (SPPG) follow a logistic roll-out whose final size, midpoint and "
     "steepness were fitted to BGN's reported counts of operational kitchens. Kitchens open after an opening delay "
     "and can be suspended; the weekly suspension fraction rises when the opening rate exceeds a sustainable "
     "opening capacity, representing strain on supervision, staff and suppliers during rapid scaling, and "
     "suspended kitchens reopen after a reinstatement time. Beneficiaries served equal operational kitchens times "
     "beneficiaries per kitchen, which follows the reported ratio up to September 2026 and then moves to an "
     "uncertain future level. Programme demand equals beneficiaries served times the menu quantity per "
     "beneficiary times a school-calendar factor: meals pause during school holidays, except for pregnant and "
     "breastfeeding mothers and young children until BGN stopped holiday distribution to all groups in June 2026 "
     "{cite:holiday2026}. Egg demand per beneficiary is the serving size times the number of egg servings per week, "
     "which rises from two to at least three on 8 June 2026 {cite:egg3x2026}."),
    ("Egg (layer) sector.", "Pullets are placed and mature into laying hens through a third-order rearing delay. "
     "Hens leave the flock through culling and disease outbreaks. Farmers place pullets to replace expected losses "
     "and to close the gap between desired and actual flock size, with a partial correction for pullets already in "
     "rearing (the supply-line weight {cite:sterman2000}). Desired flock size responds to the expected margin, "
     "formed by smoothing the market price over an expectation delay (balancing loop B1). Placements are limited by "
     "hatchery capacity."),
    ("Broiler sector.", "Day-old chicks are placed and harvested after grow-out. Placements follow smoothed demand, "
     "an inventory correction and the expected margin, limited by day-old-chick supply."),
    ("Market and price formation.", "For each commodity, market inventory accumulates production and is depleted "
     "by sales and spoilage; programme kitchens are served before households when stock is short. Household demand "
     "responds to price through a constant own-price elasticity (balancing loop B2). Price adjusts toward an "
     "indicated price that rises when inventory coverage is below normal and is pulled toward unit cost plus a "
     "normal margin, bounded by a maximum relative price that represents imports, substitutes and market "
     "operations. Unit cost depends on the feed price, which rises with the total flock (balancing loop B3) and "
     "with exogenous feed-price shocks. Under menu flexibility (policy P4), kitchens substitute other proteins when "
     "prices are high, closing a further balancing loop (B4).")]:
    B.append(r"\noindent\textbf{" + T(head) + "} " + T(txt) + "\n")
TIKZ_CLD = r"""
\begin{tikzpicture}[font=\scriptsize, v/.style={align=center, inner sep=1.5pt},
  a/.style={-{Stealth[length=1.6mm]}, semithick}, lab/.style={font=\scriptsize\bfseries, fill=white, inner sep=0.5pt},
  loop/.style={font=\scriptsize\bfseries, circle, draw, inner sep=1pt}]
\node[v] (plan) at (0,3.2) {Planned\\kitchens};
\node[v] (open) at (2.6,3.2) {Kitchen\\opening rate};
\node[v] (oper) at (5.6,3.2) {Operational\\kitchens};
\node[v] (strain) at (2.6,4.5) {Scaling\\strain};
\node[v] (susp) at (5.6,4.5) {Suspensions};
\node[v] (ben) at (8.8,3.2) {Beneficiaries\\served};
\node[v] (mbg) at (12.6,3.2) {MBG egg\\demand};
\node[v] (cal) at (12.6,4.6) {Menu and\\school calendar};
\node[v] (cov) at (12.6,0.4) {Egg inventory\\coverage};
\node[v] (price) at (8.8,0.4) {Egg price};
\node[v] (hh) at (10.7,1.8) {Household\\egg demand};
\node[v] (marg) at (5.6,0.4) {Expected\\margin};
\node[v] (des) at (2.6,0.4) {Desired\\laying hens};
\node[v] (place) at (0,-1.0) {Pullet\\placement};
\node[v] (hens) at (2.6,-2.4) {Laying\\hens};
\node[v] (prod) at (8.8,-2.4) {Egg\\production};
\node[v] (feed) at (2.6,-3.8) {Feed\\price};
\node[v] (cost) at (5.6,-3.8) {Unit\\cost};
\node[v] (ant) at (0,1.8) {Anticipated\\programme demand};
\draw[a] (plan) -- node[lab, above]{+} (open);
\draw[a] (open) -- node[lab, above]{+} (oper);
\draw[a] (open) -- node[lab, left]{+} (strain);
\draw[a] (strain) -- node[lab, above]{+} (susp);
\draw[a] (susp) -- node[lab, right]{$-$} (oper);
\draw[a] (oper) -- node[lab, above]{+} (ben);
\draw[a] (ben) -- node[lab, above]{+} (mbg);
\draw[a] (cal) -- node[lab, right]{+} (mbg);
\draw[a] (mbg) -- node[lab, right]{$-$} (cov);
\draw[a] (cov) -- node[lab, above]{$-$} (price);
\draw[a] (price) to[bend left=15] node[lab, left]{$-$} (hh);
\draw[a] (hh) to[bend left=15] node[lab, above]{$-$} (cov);
\draw[a] (price) -- node[lab, above]{+} (marg);
\draw[a] (marg) -- node[lab, above]{+} (des);
\draw[a] (des) -- node[lab, above right]{+} (place);
\draw[a] (place) -- node[lab, left]{+} node[pos=0.55, sloped]{$||$} (hens);
\draw[a] (hens) -- node[lab, above]{+} (prod);
\draw[a] (prod) -- node[lab, below right]{+} (cov);
\draw[a] (hens) -- node[lab, left]{+} (feed);
\draw[a] (feed) -- node[lab, above]{+} (cost);
\draw[a] (cost) -- node[lab, right, pos=0.12]{$-$} (marg);
\draw[a] (cost) to[bend right=20] node[lab, below right]{+} (price);
\draw[a] (plan) -- node[lab, left]{+} (ant);
\draw[a, dashed] (ant) -- node[lab, above]{+ (P3)} (des);
\draw[a, dashed] (price) to[bend right=25] node[lab, right, pos=0.72]{$-$ (P4)} (mbg);
\node[loop] at (7.3,-1.0) {B1};
\node[loop] at (11.1,0.9) {B2};
\node[loop] at (4.1,-2.9) {B3};
\node[loop] at (11.3,2.4) {B4};
\end{tikzpicture}"""
tikz_figure(TIKZ_CLD, "Causal loop diagram of the egg chain (the broiler chain is analogous). Dashed links act "
            "only under policies P3 (forward contracts) and P4 (menu flexibility); {m:||} marks the rearing delay",
            "fig:cld", wide=True)
TIKZ_SFD = r"""
\begin{tikzpicture}[font=\scriptsize, st/.style={draw, thick, minimum width=1.9cm, minimum height=0.8cm, align=center,
  fill=gray!8}, cl/.style={cloud, draw, cloud puffs=8, minimum width=0.7cm, minimum height=0.45cm, inner sep=0pt},
  fl/.style={-{Stealth[length=2mm]}, line width=2.2pt, draw=gray!70}, fll/.style={font=\scriptsize, align=center},
  inf/.style={-{Stealth[length=1.4mm]}, thin, dashed}]
% programme
\node[cl] (c0) at (0,3) {};
\node[st] (op) at (3.6,3) {Operational\\kitchens};
\node[st] (su) at (8.0,3) {Suspended\\kitchens};
\draw[fl] (c0) -- node[fll, above]{opening} (op);
\draw[fl] (op.north east) to[bend left=18] node[fll, above]{suspension} (su.north west);
\draw[fl] (su.south west) to[bend left=18] node[fll, below]{reinstatement} (op.south east);
% layers
\node[cl] (c1) at (0,0.9) {};
\node[st] (pu) at (3.6,0.9) {Pullets};
\node[st] (lh) at (8.0,0.9) {Laying\\hens};
\node[cl] (c2) at (11.2,0.9) {};
\draw[fl] (c1) -- node[fll, above]{placement} (pu);
\draw[fl] (pu) -- node[fll, below]{maturation\\(3rd-order delay)} (lh);
\draw[fl] (lh) -- node[fll, above]{culling,\\disease} (c2);
% broilers
\node[cl] (c3) at (0,-1.1) {};
\node[st] (br) at (3.6,-1.1) {Broilers in\\grow-out};
\node[cl] (c4) at (8.0,-1.1) {};
\draw[fl] (c3) -- node[fll, above]{DOC placement} (br);
\draw[fl] (br) -- node[fll, above]{harvest, mortality} (c4);
% markets

\node[st] (ei) at (14.6,0.9) {Egg\\inventory};
\node[st] (ci) at (14.6,-1.1) {Chicken\\inventory};
\node[st] (ep) at (14.6,3) {Egg and chicken\\prices};
\draw[fl] (11.2,0.15) -- (11.2,-0.1) -| (ei.south) ;
\draw[inf] (lh) to[bend right=12] node[fll, below, pos=0.6]{egg production} (ei);
\draw[inf] (br.south) |- node[fll, below, pos=0.75]{chicken production} (ci.south);
\draw[fl] (ei.east) -- ++(0.7,0) node[right, fll]{household and\\MBG sales,\\spoilage};
\draw[fl] (ci.east) -- ++(0.7,0) node[right, fll]{household and\\MBG sales,\\spoilage};
\draw[inf] (ei.north) -- node[fll, right]{coverage} (ep.south);
\draw[inf] (op.north) -- ++(0,0.75) -| node[fll, pos=0.2, above]{MBG demand (beneficiaries $\times$ menu $\times$ school calendar)} (12.7,1.25) -- (ei.north west);
\draw[inf] (ep.west) -- node[fll, above]{expected margin} (su.east);
\end{tikzpicture}"""
TIKZ_SFD = TIKZ_SFD.replace(r"\draw[fl] (11.2,0.15) -- (11.2,-0.1) -| (ei.south) ;", "")
TIKZ_SFD = TIKZ_SFD.replace(r"\draw[inf] (ep.west) -- node[fll, above]{expected margin} (su.east);",
                            r"\draw[inf] (ep.south west) to[bend right=10] node[fll, above, pos=0.35]{expected margin} (lh.north east);")
tikz_figure(TIKZ_SFD, "Simplified stock-and-flow structure (stocks as boxes, flows as thick arrows, "
            "information links and production rates computed from stocks dashed). Expected prices and the feed price "
            "are omitted for clarity",
            "fig:sfd", wide=True)
sub("Policies")
table([["P0", "Baseline", "Current roll-out; cooperative sourcing share 0.1; no forward contracts; fixed menu"],
       ["P1", "Phased roll-out", "Roll-out steepness multiplied by 1.75 (a slower S-curve)"],
       ["P2", "Cooperative sourcing", "Direct purchase share from farmer groups 0.6 (lower intermediary mark-up)"],
       ["P3", "Forward contracts", "80% of future programme demand contracted 20 weeks ahead, so farmers can expand "
        "flocks before the demand arrives"],
       ["P4", "Menu flexibility", "Up to 50% substitution of other proteins when the relative price exceeds 1.15"],
       ["P5", "Combined", "P2 + P3 + P4"]],
      ["", "Policy", "Implementation in the model"], "Policy levers",
      r"l>{\raggedright\arraybackslash}p{1.9cm}>{\raggedright\arraybackslash}X", label="tab:policies")
_steep = float(re.search(r"\nRollout steepness=\n\t([0-9.]+)", (MODEL / "mbg_poultry.mdl").read_text()).group(1))
_m = lambda s_: 2 * np.log(9) * s_ * 7 / 30.44
par(f"P1 slows the roll-out so that 10--90% of kitchens open over about {_m(1.75 * _steep):.0f} months instead of "
    f"about {_m(_steep):.0f}. P2 reflects "
    "the finding that MBG procurement runs largely through intermediaries {cite:ipb2026,ambarwati2025}. P4 "
    "formalises the reactive menu changes of November 2025 {cite:prabowo2025} as a rule.")
sub("Validation")
par("Following Barlas {cite:barlas1996} and Sterman {cite:sterman2000}, the model was subjected to dimensional "
    "consistency checks; six extreme-condition tests (no programme, ten-fold programme demand, loss of all laying "
    "hens, no hatchery expansion, doubled feed price and near-instant roll-out); an integration-error test comparing "
    "the baseline run at two time steps; an ensemble robustness test repeating all ensemble scenarios for four "
    "policies at both time steps; a parameter-recovery test applying the calibration procedure to synthetic data "
    "with known parameters; and behaviour reproduction against historical prices, assessed with MAPE, {m:R^2} and "
    "Theil inequality statistics {cite:sterman1984}.")
sub("Exploratory Ensemble and Outcome Indicators")
par(f"{N_SCEN:,} scenarios were drawn by Latin Hypercube sampling {{cite:mckay1979}} over {len(UNCERTAINTIES)} "
    "uncertain parameters (Table {ref:tab:unc}). Each policy was run on the same scenarios (common random numbers), "
    "giving a paired design, and each scenario was also run without the programme. To make the ensemble feasible at "
    "the small time step, blocks of scenarios were integrated together as arrays with the same Euler update as PySD; "
    f"before use, these runs were checked against ordinary PySD runs ({int(VEQ['runs_compared'])} runs, maximum "
    f"relative difference {VEQ['max_relative_difference']:.0e}). Price effects were measured as "
    "the difference between the two runs, so that movements caused by exogenous shocks are not attributed to the "
    "programme. Outcome indicators were the peak programme-attributable egg and chicken price rise, weeks above "
    "the threshold, mean household consumption loss, farmers' margin volatility, protein cost per portion and "
    "programme coverage in the final year. A run was labelled a spike if the programme-attributable price rise in "
    f"either commodity exceeded {pp(SPIKE_THRESHOLD, 0)} percentage points of the baseline price. The threshold is "
    f"well above the largest seasonal premium in the pre-programme data (chicken prices "
    f"{pct(sr('chicken', 'eid_pre')['coef'])} above trend before Idul Fitri; Section {{ref:sec:seas}}), so a spike "
    f"is a rise beyond normal seasonal variation; for eggs it corresponds to about Rp "
    f"{SPIKE_THRESHOLD * 28140:,.0f} per kilogram.")
URANGE = {"Rollout midpoint": "Fitted value $\\pm$ about 7 weeks", "Rollout steepness": "Fitted value $\\pm$ about 50%",
          "Target kitchens": "Fitted 29,000; BGN targets up to 32,000",
          "Future beneficiaries per kitchen": "Sep. 2026 ratio to earlier ratio; cap 2,500--3,000 {cite:cap2025}",
          "Egg serving size": "One egg, 50--65 g", "Egg servings after menu change": "Two to four per week {cite:egg3x2026}",
          "Chicken per beneficiary": "Conflicting official estimates {cite:gopan2025}",
          "Price expectation delay": "Not identifiable (Table {ref:tab:ident})",
          "Investment sensitivity": "Around calibrated value",
          "Supply line weight": "Full range {cite:sterman2000}",
          "Hatchery capacity factor": "Spare hatchery capacity",
          "DOC capacity factor": "Day-old-chick oversupply 1.05--1.4",
          "Household egg elasticity": "QUAIDS estimates {cite:khoiriyah2024}",
          "Household chicken elasticity": "QUAIDS estimates {cite:khoiriyah2024}",
          "Price sensitivity to coverage": "Not identifiable (Table {ref:tab:ident})",
          "Feed shock magnitude": "Up to +50% feed price",
          "Outbreak loss fraction": "Up to 30% of hens lost",
          "Base suspension fraction": "Fitted 0.0042; 0.5--2 times",
          "Strain sensitivity": "No data; wide range", "Kitchen opening delay": "No data; 2--8 weeks",
          "Sustainable opening capacity": "No data; wide range",
          "Intermediary margin": "BPS trade margins for eggs 13--27%",
          "Maximum relative price": "Imports, substitutes, market operations"}
table([[k, raw(f"{lo:,.4g}"), raw(f"{hi:,.4g}"), URANGE.get(k, "")] for k, (lo, hi) in UNCERTAINTIES.items()],
      ["Parameter", "Low", "High", "Basis"], "Uncertain parameters and ranges",
      r">{\raggedright\arraybackslash}p{2.6cm}rr>{\raggedright\arraybackslash}X", size=r"\scriptsize",
      label="tab:unc")
sub("Scenario Discovery and Early Warning")
par("Using baseline-policy runs, four classifiers (logistic regression, a depth-3 decision tree, a random forest "
    "{cite:breiman2001} and gradient boosting) were trained to predict spikes from the uncertain parameters and "
    "evaluated by stratified five-fold cross-validation. The decision tree provides readable rules; SHAP values on "
    "the random forest quantify each parameter's contribution and direction; PRIM identifies a region of the "
    "uncertainty space with a high spike density (the box with the highest coverage at a density of at least 0.8, "
    "reporting dimensions restricted by at least 10% of their range). The results were compared with a "
    "one-at-a-time sensitivity analysis. An early-warning classifier was trained on indicators observable 13 weeks "
    "after programme start: relative prices, inventory coverage, growth in pullet placements, the kitchen opening "
    "rate, the share of suspended kitchens and the feed price.")
sub("Policy Comparison")
par("For each policy, spike probability is reported with Wilson 95% confidence intervals {cite:wilson1927}, "
    "together with the median and 90th percentile of each outcome. Each policy is compared with P0 on the same "
    "scenarios with the Wilcoxon signed-rank test {cite:wilcoxon1945}, Holm-corrected {cite:holm1979}, with the "
    "matched-pairs rank-biserial correlation as effect size {cite:kerby2014}; spike occurrence is compared with an "
    "exact McNemar test {cite:mcnemar1947}, and all policies jointly with the Friedman test {cite:friedman1937}.")

# ================================================================== 4 DATA
sec("Data", "sec:data")
par("Table {ref:tab:data} summarises the data used to build, calibrate and validate the model. Appendix "
    "{ref:app:par} lists every parameter with its value and source.")
table([["Retail prices of eggs and chicken", "WFP market prices {cite:wfp}", "Calibration; baseline prices; "
        "seasonality", "2007--2026"],
       ["Operational SPPG", "BGN {cite:bgn2025,bgnaug2025} and press reports {cite:sppgpress}", "Roll-out fit",
        "Jan. 2025--Sep. 2026"],
       ["Beneficiaries", "BGN {cite:bgn2025,antara2026,bgnaug2025}; Kemenkeu {cite:sppgpress}",
        "Beneficiaries per kitchen", "Jan. 2025--Sep. 2026"],
       ["Kitchen suspensions", "BGN", "Suspension hazard", "to May 2026"],
       ["Egg and chicken production", "BPS {cite:bpsprod}", "Initial production", "2024"],
       ["Household price elasticities", "QUAIDS on SUSENAS {cite:khoiriyah2024}", "Household demand", "2021"],
       ["Menu and holiday rules", "BGN statements {cite:bgnegg2025,egg3x2026,holiday2026}", "Programme demand",
        "2025--2026"],
       ["Biological and cost parameters", "Breed standard {cite:lohmann}; Indonesian farm and trade statistics",
        "Production and unit cost", "various"]],
      ["Data", "Source", "Use in the model", "Period"], "Overview of data sources",
      r">{\raggedright\arraybackslash}p{2.2cm}>{\raggedright\arraybackslash}X>{\raggedright\arraybackslash}p{1.9cm}"
      r">{\raggedright\arraybackslash}p{1.3cm}", size=r"\scriptsize", label="tab:data")
sub("Prices and Seasonality", "sec:seas")
par("Monthly retail prices of chicken eggs and chicken meat were taken from the World Food Programme's Indonesia "
    "food price dataset {cite:wfp}, which covers about 200 markets. Because the set of reporting markets varies, "
    "each market's price was expressed relative to its own 2024 mean, and the national index for each month is the "
    "median of these relatives. Months with fewer than 100 reporting markets, and the incomplete latest month, were "
    "excluded, leaving 29 monthly observations from January 2024 to October 2026. Baseline prices were set to the "
    "2024 mean of monthly national medians (Rp 28,140/kg for eggs and Rp 35,704/kg for chicken).")
par("The model contains no seasonal household demand, so seasonality was removed before calibration. Using the "
    "WFP national series for 2007--2023 (March 2020 to December 2021 excluded), the log ratio of price to its "
    "centred 12-month moving average was regressed on calendar-month dummies and on the shares of the 30 days "
    "before and after Idul Fitri falling in each month, with HAC standard errors {cite:neweywest1987}. Before Idul "
    f"Fitri, egg prices are {pct(sr('egg', 'eid_pre')['coef'])} above trend (p = {sr('egg', 'eid_pre')['p']:.3f}) "
    f"and chicken prices {pct(sr('chicken', 'eid_pre')['coef'])} above trend (p < 0.001). The fitted seasonal "
    "factors were divided out of the 2024--2026 series.")
sub("Programme Data")
par(f"Operational SPPG counts were compiled for {len(roll) + 1} dates from January 2025 to September 2026 from BGN "
    "releases and press reports of BGN statements {cite:bgn2025,bgnaug2025,sppgpress}. Reported beneficiaries per "
    "operational kitchen were about 2,700--3,200 until February 2026 but about 2,000 in September 2026 (53--57 "
    "million beneficiaries in 27,485 kitchens) {cite:sppgpress}; the model follows the observed ratio and treats "
    "the later level as uncertain, bounded by BGN's cap of 2,500 portions per kitchen (3,000 with certified cooks) "
    "{cite:cap2025}. Suspension parameters were fitted to BGN's report that 8,182 SPPG had been suspended at "
    "some point and 2,213 remained inactive at the end of May 2026, giving a weekly suspension hazard of about 0.4% "
    "and a mean reinstatement time of about 15 weeks.")
par("Egg servings follow BGN's planning assumption of two egg dishes a week {cite:bgnegg2025} until 8 June 2026 "
    "and at least three afterwards {cite:egg3x2026}. No menu specification for chicken has been published, and "
    "official estimates of programme chicken demand conflict, from about 0.04 to 0.26 kg per beneficiary per week "
    "{cite:gopan2025}; chicken quantity is therefore treated as a deep uncertainty. Initial production was set from "
    "BPS 2024 figures: 6,342,705 t of eggs and 3,835,917 t of broiler meat (preliminary) {cite:bpsprod}. Household "
    "own-price elasticities were set from QUAIDS estimates on SUSENAS 2021 data ({m:-0.669} for eggs and "
    "{m:-1.581} for poultry) {cite:khoiriyah2024}. Layer parameters (point of lay at about 18 weeks, laying period "
    "of about 65 weeks, hen-day production of about 84.5%) follow the breed standard {cite:lohmann} and Indonesian "
    "farm practice; feed is 60--70% of production cost and trader mark-ups follow BPS trade and transport margins "
    "for eggs (13--27% in 2017--2021).")
sub("Calibration")
par("The investment sensitivities of layer and broiler farmers were estimated jointly on the seasonally adjusted "
    "egg and chicken series by minimising the sum of squared errors (Nelder--Mead, four starting points). Two "
    "further parameters, the price-expectation delay and the sensitivity of price to inventory coverage, are not "
    "identifiable from these data: the fit error changes little across wide ranges of either (Table "
    "{ref:tab:ident}). They were fixed at 8 weeks and 1.0, values that do not depend on the data, and explored over "
    "wide ranges in the ensemble.")

# ================================================================== 5 RESULTS
sec("Results", "sec:results")
sub("Validation and Calibration", "sec:val")
n_a = len(a_tests); n_a_pass = int((a_tests["Pass"].astype(str) == "True").sum())
b1_pass = str(b1["Pass"]) == "True"
pr_max = rec["abs_error_%"].max()
inv, binv = cal.loc["Investment sensitivity"], cal.loc["Broiler investment sensitivity"]
par(f"{n_a_pass} of the {n_a} extreme-condition tests passed (Table {{ref:tab:val}}). The integration-error test "
    f"gave a maximum difference of {b1['Observed']} of each variable's range between time steps of {DT:g} and "
    f"{DT / 2:g} week ({'within' if b1_pass else 'above'} the 1% criterion), and "
    f"{pct(tsr['spike_agreement'])} of ensemble runs received the same spike classification at both time steps. "
    f"The parameter-recovery test recovered all parameters within {pr_max:.1f}% of their true values. The "
    f"calibrated layer investment sensitivity is {inv['estimate']:.2f}; the broiler investment sensitivity is "
    f"{binv['estimate']:.3f}" + (", at the lower bound of zero" if str(binv["at_bound"]) == "True" else "") + ".")
par(f"On the seasonally adjusted series the model reproduces egg prices with a MAPE of {pct(EGG['MAPE'])} and an "
    f"{{m:R^2}} of {EGG['R2']:.2f}, and chicken prices with a MAPE of {pct(CHK['MAPE'])} and an {{m:R^2}} of "
    f"{CHK['R2']:.2f} (Table {{ref:tab:beh}}, Figure {{ref:fig:beh}}). The bias proportion of the error "
    f"({{m:U_M}}) is {EGG['Um']:.3f} for eggs and {CHK['Um']:.3f} for chicken, and most of the error is "
    f"unsystematic ({{m:U_C}} = {EGG['Uc']:.2f} and {CHK['Uc']:.2f}).")
table([[raw(esc(r.Index)), raw(esc(r._1)), raw(esc(r.Observed)), "Pass" if str(r.Pass) == "True" else "Fail"]
       for r in val.itertuples()],
      ["Test", "Pass criterion", "Observed", "Result"], "Validation tests",
      r">{\raggedright\arraybackslash}X>{\raggedright\arraybackslash}X>{\raggedright\arraybackslash}p{3.2cm}l",
      wide=True, size=r"\scriptsize", label="tab:val")
ip = read("identifiability_profile.csv")
table([[r["parameter"], r["value"], raw(f"{r['SSE']:.5f}")] for _, r in ip.iterrows()],
      ["Fixed parameter", "Value", "SSE"], "Identifiability profile: fit error when one fixed parameter is varied",
      r">{\raggedright\arraybackslash}Xrr", size=r"\scriptsize", fmt=1, label="tab:ident")
table([[k] + [raw(f"{r[c]:.3f}") for c in ["MAPE", "R2", "Um", "Us", "Uc"]] for k, r in beh.iterrows()],
      ["Series", "MAPE", "{m:R^2}", "{m:U_M}", "{m:U_S}", "{m:U_C}"], "Behaviour reproduction against historical prices",
      r">{\raggedright\arraybackslash}Xrrrrr", size=r"\scriptsize", label="tab:beh")
figure("fig_behaviour_reproduction.png", "Simulated and observed (seasonally adjusted) relative prices", wide=True,
       label="fig:beh")
sub("Baseline Dynamics")
pk_e_w, pk_c_w = _ex_egg.idxmax(), _ex_chk.idxmax()
par(f"Figure {{ref:fig:base}} compares the calibrated baseline with the same run without the programme. The "
    f"programme-attributable egg price rise peaks at {pp(BASE['peak_egg_price'])} percentage points in "
    f"{wdate(pk_e_w)} and the chicken price rise at {pp(BASE['peak_chicken_price'])} percentage points in "
    f"{wdate(pk_c_w)}. The egg price exceeds the counterfactual by more than {pp(SPIKE_THRESHOLD, 0)} points for "
    f"{BASE['weeks_egg_above_thr']} weeks and the chicken price for {BASE['weeks_chicken_above_thr']} weeks. "
    f"Average household consumption over the programme period is {pct(BASE['hh_egg_loss'])} lower for eggs and "
    f"{pct(BASE['hh_chicken_loss'])} lower for chicken than without the programme. School holidays produce short, "
    "sharp drops in programme demand that are visible in the price paths.")
figure("fig_baseline_dynamics.png", "Baseline dynamics with and without the programme", wide=True, label="fig:base")
sub("Conditions Leading to Programme-Attributable Spikes", "sec:spikes")
par(f"Under the baseline policy, {pct(P0['spike_prob'])} of scenarios produce a spike (95% CI "
    f"{pct(P0['spike_ci_low'])}--{pct(P0['spike_ci_high'])}). The spike outcome is predictable from the uncertain "
    f"inputs: {best_clf.lower()} reaches a cross-validated ROC AUC of {cb.loc[best_clf, 'roc_auc_mean']:.3f}, "
    f"against {cb.loc['Logistic regression', 'roc_auc_mean']:.3f} for logistic regression and "
    f"{cb.loc['CART (depth 3)', 'roc_auc_mean']:.3f} for a depth-3 tree (Table {{ref:tab:clf}})." + (
        " The gap between the linear and the tree-ensemble models indicates interactions between inputs."
        if cb["roc_auc_mean"].max() - cb.loc["Logistic regression", "roc_auc_mean"] > 0.02 else ""))
par(f"SHAP values (Figure {{ref:fig:shap}}) rank {pn(shap.index[0])}, {pn(shap.index[1])} and {pn(shap.index[2])} "
    f"as the main drivers. The PRIM box (Table {{ref:tab:prim}}) covers {pct(BOX['coverage'], 0)} of all spikes with "
    f"a spike density of {pct(BOX['density'], 0)}, against {pct(P0['spike_prob'], 0)} in the whole ensemble, and "
    "restricts " + " and ".join(f"{pn(k)} (to {r['lower']:,.3g}--{r['upper']:,.3g})" for k, r in prim_m.iterrows())
    + ". The one-at-a-time analysis (Figure {ref:fig:oat}) ranks " + ", ".join(pn(k) for k in oat_top.index[:3])
    + f" highest; its ranking " + ("correlates only weakly" if RHO < 0.5 else "correlates moderately" if RHO < 0.7
                                   else "agrees") + f" with the SHAP ranking (Spearman {{m:\\rho}} = {RHO:.2f})" + (
        ", because one-at-a-time variation around the base case cannot reveal effects that appear only in "
        "combination." if RHO < 0.7 else "."))
table([[k] + [raw(f"{r[m + '_mean']:.3f} $\\pm$ {r[m + '_sd']:.3f}") for m in ["accuracy", "f1", "roc_auc"]]
       for k, r in cb.iterrows()],
      ["Classifier", "Accuracy", "F1", "ROC AUC"], "Spike classifiers (five-fold cross-validation, mean {m:\\pm} SD)",
      r">{\raggedright\arraybackslash}Xccc", size=r"\scriptsize", label="tab:clf")
figure("fig_shap_summary.png", "SHAP summary for the random-forest spike classifier", label="fig:shap")
table([[pn(k)[0].upper() + pn(k)[1:], raw(f"{r['lower']:,.3g}"), raw(f"{r['upper']:,.3g}"),
        raw(f"{r['full_range_low']:,.3g}--{r['full_range_high']:,.3g}"),
        raw(f"{100 * r['share_of_range_removed']:.0f}\\%")] for k, r in prim.iterrows()],
      ["Parameter", "Box low", "Box high", "Full range", "Removed"],
      f"PRIM box (coverage {BOX['coverage']:.2f}, density {BOX['density']:.2f}, mass {BOX['mass']:.2f})",
      r">{\raggedright\arraybackslash}Xrrrr", size=r"\scriptsize", label="tab:prim")
figure("fig_prim_tradeoff.png", "PRIM peeling trajectory (coverage versus density)", label="fig:prim")
verbatim(cart_rules, "Decision-tree rules for spike occurrence (class 1 = spike)", label="fig:cart")
figure("fig_oat_tornado.png", "One-at-a-time sensitivity of peak programme-attributable price rise", label="fig:oat")
sub("Early-Warning Indicators", "sec:ew")
first_split = re.search(r"\|--- (\w+)", ew_rules).group(1).replace("obs_", "").replace("_", " ")
par(f"Indicators observed 13 weeks after programme start predict later spikes "
    f"{'only moderately' if ew['roc_auc_mean'].max() < 0.85 else 'well'} (Table "
    f"{{ref:tab:ew}}): the random forest reaches a ROC AUC of {ew.loc['Random forest', 'roc_auc_mean']:.3f} and a "
    f"depth-2 tree {ew.loc['CART (depth 2)', 'roc_auc_mean']:.3f}. The first split of the tree uses the {first_split} "
    "(Figure {ref:fig:ewrules})." + (" At that point programme demand is still small relative to supply, so the "
    "market signals that would warn of a later spike have not yet formed." if ew["roc_auc_mean"].max() < 0.85 else ""))
table([[k] + [raw(f"{r[m]:.3f}") for m in ["accuracy_mean", "f1_mean", "roc_auc_mean"]] for k, r in ew.iterrows()],
      ["Classifier", "Accuracy", "F1", "ROC AUC"],
      "Early-warning classifiers using indicators observed 13 weeks after programme start",
      r">{\raggedright\arraybackslash}Xccc", size=r"\scriptsize", label="tab:ew")
verbatim(ew_rules, "Early-warning decision-tree rules", label="fig:ewrules")
sub("Policy Comparison", "sec:policy")
lines = []
for k in ps.index:
    if k == "P0 Baseline":
        continue
    m = mc.loc[k]
    lines.append(f"{SHORT[k]} ({LABEL[k].lower()}) {pct(spike[k])}, removing {int(m.iloc[0]):,} spikes and adding "
                 f"{int(m.iloc[1]):,}")
cost0 = P0["mean_cost_per_portion_median"]
lab_ = {"peak_egg_price": "Peak egg price", "peak_chicken_price": "Peak chicken price",
        "hh_egg_loss": "Household egg loss", "mean_cost_per_portion": "Cost per portion"}
_ns = wx[wx["outcome"].isin(lab_) & ~wx["significant_0.05"].astype(str).eq("True")]
par(f"Table {{ref:tab:pol}} and Figure {{ref:fig:pol}} compare the policies. Against {pct(P0['spike_prob'])} under "
    "P0, the spike probability is " + "; ".join(lines) + " (Table {ref:tab:mcn}). Median protein cost per portion is "
    f"Rp {cost0:,.0f} under P0, Rp {ps.loc['P2 Cooperative sourcing', 'mean_cost_per_portion_median']:,.0f} under "
    f"P2 and Rp {ps.loc['P5 Combined (P2+P3+P4)', 'mean_cost_per_portion_median']:,.0f} under P5. Programme "
    + ("coverage in the final year is the same under all policies. " if ps["mean_coverage_last52_median"].round(2).nunique() == 1
       else "coverage in the final year differs little between policies. ")
    + ("Differences from P0 that are not significant after Holm correction: "
       + "; ".join(f"{SHORT[r.policy]} on {lab_[r.outcome].lower()}" for r in _ns.itertuples()) + ". "
       if len(_ns) else "All differences from P0 are significant after Holm correction. ")
    + ("The Friedman test rejects equal outcomes across policies for every indicator tested (p < 0.001)."
       if (fr["p"] < 0.001).all() else ""))
table([[SHORT.get(k, k), raw(f"{r['spike_prob']:.3f}"), raw(f"{r['spike_ci_low']:.3f}--{r['spike_ci_high']:.3f}"),
        raw(f"{r['peak_egg_price_median']:.3f}"), raw(f"{r['peak_egg_price_p90']:.3f}"),
        raw(f"{r['peak_chicken_price_median']:.3f}"), raw(f"{r['hh_egg_loss_median']:.4f}"),
        raw(f"{r['mean_cost_per_portion_median']:,.0f}"), raw(f"{r['mean_coverage_last52_median']:.2f}")]
       for k, r in ps.iterrows()],
      ["Policy", "Spike prob.", "95% CI", "Peak egg (median)", "Peak egg (P90)", "Peak chicken (median)",
       "Household egg loss", "Cost per portion (Rp)", "Coverage, final year"],
      "Policy outcomes across scenarios (price effects are programme-attributable relative rises)",
      r"l" + r">{\centering\arraybackslash}X" * 8, wide=True, size=r"\scriptsize", label="tab:pol")
lab = {"peak_egg_price": "Peak egg price", "peak_chicken_price": "Peak chicken price",
       "hh_egg_loss": "Household egg loss", "mean_cost_per_portion": "Cost per portion"}
w = wx[wx["outcome"].isin(lab)]
table([[lab[r["outcome"]], SHORT.get(r["policy"], r["policy"]), raw(f"{r['median_diff']:.4g}"),
        raw(f"{r['rank_biserial']:.3f}"), raw(pval(r["p_holm"]))] for _, r in w.iterrows()],
      ["Outcome", "Policy", "Median diff.", "Rank-biserial r", "Holm p"],
      "Paired comparison with P0 (Wilcoxon signed-rank)", r">{\raggedright\arraybackslash}Xcrrr",
      size=r"\scriptsize", label="tab:wil")
table([[SHORT.get(k, k), int(r.iloc[0]), int(r.iloc[1]), raw(pval(r.iloc[2]))] for k, r in mc.iterrows()],
      ["Policy", "Spikes removed", "Spikes added", "{m:p} (exact)"],
      "Change in spike occurrence relative to P0 (McNemar)", r"lrrr", size=r"\scriptsize", label="tab:mcn")
figure("fig_policy_comparison.png", "Policy comparison across scenarios", wide=True, label="fig:pol")
figure("fig_policy_tradeoff.png", "Protein cost per portion versus spike probability", label="fig:trade")

# ================================================================== 6-8 (written from the final results)
exec((HERE / "paper_discussion.py").read_text())

B.append(r"\clearpage")
B.append(r"\section*{Declarations}")
for lab_, txt in [
        ("Funding", "This research received no external funding."),
        ("Competing interests", "The author declares no competing interests."),
        ("Data and code availability", "The Vensim model, the Python analysis code, the price extract and the "
         "programme data with their sources are available from the author's repository "
         "(github.com/daniel766hi/kaggle-compe, folder paper/)."),
        ("Use of AI tools", "An AI assistant (Claude, Anthropic) was used to help develop the simulation and analysis "
         "code, collect and process public data, and draft and edit the text. The author reviewed, revised and "
         "verified all content, including every equation, data source and reference, and takes full responsibility "
         "for the work.")]:
    B.append(rf"\noindent\textbf{{{lab_}:}} " + T(txt) + "\n")

# ================================================================== APPENDICES
APP = [r"\onecolumn", r"\appendix", r"\section{Model Equations}\label{app:eq}", r"\scriptsize",
       r"\begin{longtable}{>{\raggedright\arraybackslash}p{4.2cm}>{\raggedright\arraybackslash\ttfamily}p{8.9cm}"
       r">{\raggedright\arraybackslash}p{2.4cm}}", r"\toprule \textbf{Variable} & \textbf{Equation} & \textbf{Units} \\ "
       r"\midrule \endhead"]
text = (MODEL / "mbg_poultry.mdl").read_text().split("\\\\\\---///")[0].replace("{UTF-8}", "")
for block in text.split("|"):
    m = re.match(r"\s*(.+?)=\s*\n\t(.+?)\n\t~\t(.*?)\n\t~\t(.*?)\s*$", block, re.S)
    if m:
        var, eq, units = (re.sub(r"\s+", " ", x.strip()) for x in m.groups()[:3])
        if len(eq) > 600:
            eq = eq[:600] + " ..."
        APP.append(f"{esc(var)} & {esc(eq)} & {esc(units)} \\\\")
APP += [r"\bottomrule", r"\end{longtable}", r"\normalsize", r"\section{Parameters and Sources}\label{app:par}",
        r"\scriptsize", r"\begin{longtable}{>{\raggedright\arraybackslash}p{4.2cm}r>{\raggedright\arraybackslash}p{2.4cm}"
        r">{\raggedright\arraybackslash}p{7.2cm}}",
        r"\toprule \textbf{Parameter} & \textbf{Value} & \textbf{Units} & \textbf{Source or basis} \\ \midrule \endhead"]
psheet = pd.read_csv(MODEL / "data" / "parameter_sheet.csv").fillna("")
for _, r in psheet.iterrows():
    src = r["source"] or r["comment"]
    APP.append(f"{esc(r['parameter'])} & {esc(r['model_value'])} & {esc(r['units'])} & {esc(src)} \\\\")
APP += [r"\bottomrule", r"\end{longtable}", r"\normalsize"]

# ================================================================== ASSEMBLE
abstract_tex = T(ABSTRACT)
bib = [r"\begin{thebibliography}{99}", r"\small"] + [rf"\bibitem{{{k}}} " + REFS[k] for k in CITED] + \
      [r"\end{thebibliography}"]
unused = sorted(set(REFS) - set(CITED))
if unused:
    print("references defined but not cited (dropped):", unused)
stamp_cmd = (r"\fancyfoot[L]{\scriptsize\color{red}" + esc(STAMP) + "}") if STAMP else ""
PRE = rf"""\documentclass[10pt,twocolumn,a4paper]{{article}}
\usepackage[utf8]{{inputenc}}
\usepackage[T1]{{fontenc}}
\usepackage{{times}}
\usepackage{{textcomp}}
\usepackage[margin=2.1cm,columnsep=0.65cm]{{geometry}}
\usepackage{{amsmath}}
\usepackage{{graphicx}}
\usepackage{{booktabs,tabularx,array,longtable}}
\usepackage{{xcolor}}
\usepackage{{tikz}}
\usetikzlibrary{{arrows.meta,positioning,shapes.symbols}}
\usepackage[font=small,labelsep=colon,skip=4pt]{{caption}}
\usepackage{{enumitem}}
\usepackage{{cite}}
\usepackage{{fancyhdr}}
\usepackage[hidelinks]{{hyperref}}
\usepackage{{xurl}}
\setlist{{nosep,leftmargin=*}}
\DeclareUnicodeCharacter{{2212}}{{\ensuremath{{-}}}}
\DeclareUnicodeCharacter{{2265}}{{\ensuremath{{\geq}}}}
\DeclareUnicodeCharacter{{2264}}{{\ensuremath{{\leq}}}}
\DeclareUnicodeCharacter{{00D7}}{{\ensuremath{{\times}}}}
\DeclareUnicodeCharacter{{00B2}}{{\textsuperscript{{2}}}}
\DeclareUnicodeCharacter{{2248}}{{\ensuremath{{\approx}}}}
\DeclareUnicodeCharacter{{2192}}{{\ensuremath{{\rightarrow}}}}
\pagestyle{{fancy}}\fancyhf{{}}\renewcommand{{\headrulewidth}}{{0pt}}
\fancyfoot[C]{{\thepage}}{stamp_cmd}
\fancypagestyle{{plain}}{{\fancyhf{{}}\fancyfoot[C]{{\thepage}}{stamp_cmd}}}
\begin{{document}}
\twocolumn[{{%
\centering
{{\LARGE\bfseries {esc(TITLE)}\par}}
\vspace{{1.1em}}
{{\large {esc(AUTHOR)}\textsuperscript{{1*}}\par}}
\vspace{{0.3em}}
{{\small\itshape \textsuperscript{{1}}{esc(AFFILIATION)}\par
\textsuperscript{{*}}Corresponding author. Email: {esc(EMAIL)}\par}}
{(r'\vspace{0.5em}{\small\bfseries\color{red}' + esc(STAMP) + r'\par}') if STAMP else ''}
\vspace{{1.6em}}
{{\bfseries Abstract\par}}
\vspace{{0.5em}}
\begin{{minipage}}{{0.86\textwidth}}\small
{abstract_tex}

\smallskip\noindent\textbf{{Keywords:}} {esc(KEYWORDS)}
\end{{minipage}}
\vspace{{2em}}
}}]
"""
TEX_DIR.mkdir(exist_ok=True)
tex = PRE + "\n\n".join(B) + "\n\n" + "\n".join(bib) + "\n\n" + "\n".join(APP) + "\n\\end{document}\n"
(TEX_DIR / "MBG_paper.tex").write_text(tex)
print("wrote", TEX_DIR / "MBG_paper.tex", f"({len(CITED)} references)")
for _ in range(2):
    r = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "MBG_paper.tex"],
                       cwd=TEX_DIR, capture_output=True, text=True)
    if r.returncode:
        print(r.stdout[-3000:])
        sys.exit("pdflatex failed; see latex/MBG_paper.log")
shutil.copy(TEX_DIR / "MBG_paper.pdf", PDF_DST)
print("saved", PDF_DST)
