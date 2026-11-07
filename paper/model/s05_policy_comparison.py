"""Step 5: policy comparison on the common scenario set (paired design).

- Summary per policy: median, 10th and 90th percentile of each outcome.
- Spike probability with Wilson 95% confidence interval.
- Paired Wilcoxon signed-rank test vs P0 for each outcome, Holm-corrected,
  with matched-pairs rank-biserial correlation as effect size.
- McNemar exact test for the paired binary spike outcome vs P0.
- Friedman test across all policies.
"""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import binomtest, friedmanchisquare, wilcoxon
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.proportion import proportion_confint

from common import OUT_DIR, OUTCOME_LABELS, OUTCOMES, POLICIES, is_spike, save_table, stamp

res = pd.read_csv(OUT_DIR / "ensemble_results.csv")
res = res[res["ok"]].copy()
res["spike"] = is_spike(res).astype(int)
pols = list(POLICIES)
wide = {o: res.pivot(index="scenario", columns="policy", values=o)[pols].dropna() for o in OUTCOMES + ["spike"]}

# ---------------------------------------------------------------- summary
summ = []
for p in pols:
    d = res[res["policy"] == p]
    row = {"policy": p, "n": len(d)}
    k = int(d["spike"].sum())
    lo, hi = proportion_confint(k, len(d), method="wilson")
    row.update({"spike_prob": k / len(d), "spike_ci_low": lo, "spike_ci_high": hi})
    for o in OUTCOMES:
        row[f"{o}_median"] = d[o].median()
        row[f"{o}_p10"] = d[o].quantile(0.1)
        row[f"{o}_p90"] = d[o].quantile(0.9)
    summ.append(row)
summ = pd.DataFrame(summ).set_index("policy")
save_table(summ, "policy_summary.csv")
print(summ[["spike_prob", "spike_ci_low", "spike_ci_high", "peak_egg_price_median", "peak_egg_price_p90",
            "peak_chicken_price_median", "mean_cost_per_portion_median", "mean_coverage_last52_median"]]
      .round(3).to_string())

# ---------------------------------------------------------------- paired tests vs P0
tests = []
for o in OUTCOMES:
    w = wide[o]
    for p in pols[1:]:
        d = (w[p] - w["P0 Baseline"]).values
        nz = d[d != 0]
        if len(nz) < 10:
            tests.append({"outcome": o, "policy": p, "n_pairs": len(d), "median_diff": float(np.median(d)),
                          "W": np.nan, "p_raw": 1.0, "rank_biserial": 0.0})
            continue
        stat = wilcoxon(nz)
        ranks = pd.Series(np.abs(nz)).rank().values
        rb = (ranks[nz > 0].sum() - ranks[nz < 0].sum()) / ranks.sum()
        tests.append({"outcome": o, "policy": p, "n_pairs": len(d), "median_diff": float(np.median(d)),
                      "W": stat.statistic, "p_raw": stat.pvalue, "rank_biserial": rb})
tests = pd.DataFrame(tests)
tests["p_holm"] = multipletests(tests["p_raw"], method="holm")[1]
tests["significant_0.05"] = tests["p_holm"] < 0.05
save_table(tests.set_index(["outcome", "policy"]), "policy_wilcoxon_vs_P0.csv")

mc = []
for p in pols[1:]:
    a, b = wide["spike"]["P0 Baseline"], wide["spike"][p]
    n01, n10 = int(((a == 0) & (b == 1)).sum()), int(((a == 1) & (b == 0)).sum())
    pv = binomtest(n10, n01 + n10, 0.5).pvalue if n01 + n10 else 1.0
    mc.append({"policy": p, "spike_removed (P0=1,P=0)": n10, "spike_added (P0=0,P=1)": n01, "p_exact": pv})
mc = pd.DataFrame(mc).set_index("policy")
save_table(mc, "policy_mcnemar_spike.csv")

fr = []
for o in ["peak_egg_price", "peak_chicken_price", "hh_egg_loss", "mean_cost_per_portion"]:
    s = friedmanchisquare(*[wide[o][p] for p in pols])
    fr.append({"outcome": o, "chi2": s.statistic, "p": s.pvalue})
fr = pd.DataFrame(fr).set_index("outcome")
save_table(fr, "policy_friedman.csv")
print("\nMcNemar (spike vs P0):\n", mc.to_string(), "\n\nFriedman:\n", fr.to_string())
print("\nWilcoxon vs P0 (peak egg price):\n",
      tests[tests.outcome == "peak_egg_price"][["policy", "median_diff", "rank_biserial", "p_holm"]].round(4).to_string())

# ---------------------------------------------------------------- figures
short = [p.split(" ")[0] for p in pols]
fig, ax = plt.subplots(1, 3, figsize=(15, 4.8))
for a, o in zip(ax[:2], ["peak_egg_price", "peak_chicken_price"]):
    a.boxplot([wide[o][p] for p in pols], showfliers=False)
    a.set_xticks(range(1, len(pols) + 1), short)
    a.set_title(OUTCOME_LABELS[o], fontsize=10)
err = np.vstack([summ["spike_prob"] - summ["spike_ci_low"], summ["spike_ci_high"] - summ["spike_prob"]])
ax[2].bar(short, summ["spike_prob"], yerr=err, capsize=4, color="tab:red", alpha=0.7)
ax[2].set_title("Spike probability (Wilson 95% CI)", fontsize=10); ax[2].set_ylim(0, 1)
stamp(fig); fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(OUT_DIR / "fig_policy_comparison.png", dpi=150)

fig, ax = plt.subplots(figsize=(7, 5))
ax.scatter(summ["mean_cost_per_portion_median"], summ["spike_prob"], s=80)
for p, s in zip(pols, short):
    ax.annotate(s, (summ.loc[p, "mean_cost_per_portion_median"], summ.loc[p, "spike_prob"]),
                xytext=(6, 4), textcoords="offset points")
ax.set_xlabel("Median protein cost per portion (Rp)"); ax.set_ylabel("Spike probability")
ax.set_title("Policy trade-off: programme cost vs price-stability risk")
stamp(fig); fig.tight_layout(); fig.savefig(OUT_DIR / "fig_policy_tradeoff.png", dpi=150)
print("\nsaved figures to", OUT_DIR)
