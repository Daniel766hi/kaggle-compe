"""Step 4: machine-learning scenario discovery on the baseline-policy ensemble.

A. Classifier benchmark (logistic regression, CART, random forest, gradient boosting), 5-fold CV.
B. Interpretable rules (CART depth 3).
C. SHAP explanation of the random forest.
D. PRIM boxes (Friedman & Fisher 1999; Bryant & Lempert 2010) via EMA Workbench.
E. One-at-a-time (OAT) sensitivity for comparison with A-D.
F. Early-warning classifier on indicators observable 13 weeks after programme start.
"""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import shap
from scipy.stats import spearmanr
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_validate
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier, export_text, plot_tree

from common import (CF_COLS, OBSERVABLES, OUT_DIR, POLICIES, SPIKE_THRESHOLD, UNCERTAINTIES,
                    compute_outcomes, counterfactual_params, is_spike, run, save_table, stamp)

SEED = 7
res = pd.read_csv(OUT_DIR / "ensemble_results.csv")
res = res[res["ok"]]
base = res[res["policy"] == "P0 Baseline"].reset_index(drop=True)
X = base[list(UNCERTAINTIES)]
y = is_spike(base).astype(int)
print(f"Baseline-policy runs: {len(base)}; spike share: {y.mean():.2%} (threshold +{SPIKE_THRESHOLD:.0%})")

cv = StratifiedKFold(5, shuffle=True, random_state=SEED)
scoring = ["accuracy", "f1", "roc_auc"]

# ------------------------------------------------------------------ A. benchmark
models = {
    "Logistic regression": make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)),
    "CART (depth 3)": DecisionTreeClassifier(max_depth=3, min_samples_leaf=10, random_state=SEED),
    "Random forest": RandomForestClassifier(500, min_samples_leaf=3, random_state=SEED, n_jobs=-1),
    "Gradient boosting": GradientBoostingClassifier(random_state=SEED),
}
rows = []
for name, m in models.items():
    s = cross_validate(m, X, y, cv=cv, scoring=scoring)
    rows.append({"model": name, **{f"{k}_mean": s[f"test_{k}"].mean() for k in scoring},
                 **{f"{k}_sd": s[f"test_{k}"].std() for k in scoring}})
bench = pd.DataFrame(rows).set_index("model")
save_table(bench, "sd_classifier_benchmark.csv")
print("\nA. Classifier benchmark (5-fold CV):\n", bench.round(3).to_string())

def draw_tree(tree, names, title, fname, size, precision=2, fontsize=12):
    """Tree diagram: each node shows its split, number of scenarios and share without / with a spike."""
    fig, ax = plt.subplots(figsize=size)
    plot_tree(tree, feature_names=names, class_names=["No spike", "Spike"], filled=True, rounded=True,
              impurity=False, proportion=True, precision=precision, fontsize=fontsize, ax=ax)
    ax.set_title(title, fontsize=fontsize + 1)
    stamp(fig); fig.tight_layout(); fig.savefig(OUT_DIR / fname, dpi=200); plt.close(fig)


# ------------------------------------------------------------------ B. CART rules
cart = models["CART (depth 3)"].fit(X, y)
rules = export_text(cart, feature_names=list(X.columns), show_weights=True)
(OUT_DIR / "sd_cart_rules.txt").write_text(rules)
draw_tree(cart, list(X.columns), "Decision tree for spike occurrence (baseline policy, depth 3)",
          "fig_sd_tree.png", (15, 7))
print("\nB. CART rules:\n", rules)

# ------------------------------------------------------------------ C. SHAP
rf = models["Random forest"].fit(X, y)
sv = shap.TreeExplainer(rf).shap_values(X)
sv = sv[..., 1] if np.ndim(sv) == 3 else (sv[1] if isinstance(sv, list) else sv)
imp = pd.Series(np.abs(sv).mean(0), index=X.columns).sort_values(ascending=False)
save_table(imp.rename("mean_abs_shap").to_frame(), "sd_shap_importance.csv")
plt.figure()
shap.summary_plot(sv, X, show=False, max_display=12)
fig = plt.gcf(); fig.set_size_inches(9, 6); stamp(fig); fig.tight_layout()
fig.savefig(OUT_DIR / "fig_shap_summary.png", dpi=150); plt.close(fig)
print("\nC. Mean |SHAP| (top 8):\n", imp.head(8).round(4).to_string())

# ------------------------------------------------------------------ D. PRIM
from ema_workbench.analysis import prim  # noqa: E402

p = prim.Prim(X.copy(), y.values.astype(bool), peel_alpha=0.05)
box = p.find_box()
traj = box.peeling_trajectory
# Density target: at least halfway between the spike base rate and 1. A fixed target (e.g. 0.8)
# selects the whole space when spikes are already that common.
base_rate = float(y.mean())
dens_thr = base_rate + (1 - base_rate) / 2
ok = traj[traj["density"] >= dens_thr]
i = int(ok["coverage"].idxmax()) if len(ok) else int(traj["density"].idxmax())
lims = box.box_lims[i]
restricted = [c for c in X.columns
              if not (np.isclose(lims.loc[0, c], X[c].min()) and np.isclose(lims.loc[1, c], X[c].max()))]
prim_tbl = pd.DataFrame({"lower": lims.loc[0, restricted], "upper": lims.loc[1, restricted],
                         "full_range_low": [UNCERTAINTIES[c][0] for c in restricted],
                         "full_range_high": [UNCERTAINTIES[c][1] for c in restricted]})
width = np.array([UNCERTAINTIES[c][1] - UNCERTAINTIES[c][0] for c in restricted])
prim_tbl["share_of_range_removed"] = 1 - (prim_tbl["upper"] - prim_tbl["lower"]).values / width
prim_tbl = prim_tbl.sort_values("share_of_range_removed", ascending=False)
# Report dimensions cut by >= 10% of their range as the meaningful restrictions.
prim_tbl["meaningful"] = prim_tbl["share_of_range_removed"] >= 0.10
save_table(prim_tbl, "sd_prim_box.csv")
save_table(traj, "sd_prim_trajectory.csv")
save_table(pd.Series({"base_rate": base_rate, "density_threshold": dens_thr}, name="value").to_frame(),
           "sd_prim_settings.csv")
fig, ax = plt.subplots(figsize=(6, 4.5))
sc = ax.scatter(traj["coverage"], traj["density"], c=traj["res_dim"], cmap="viridis")
ax.scatter(traj.loc[i, "coverage"], traj.loc[i, "density"], s=160, facecolors="none", edgecolors="red")
ax.set_xlabel("Coverage"); ax.set_ylabel("Density"); fig.colorbar(sc, label="Restricted dimensions")
ax.set_title("PRIM peeling trajectory (selected box circled)")
stamp(fig); fig.tight_layout(); fig.savefig(OUT_DIR / "fig_prim_tradeoff.png", dpi=150); plt.close(fig)
print(f"\nD. PRIM (density target {dens_thr:.3f}) box #{i}: coverage={traj.loc[i, 'coverage']:.2f}, density={traj.loc[i, 'density']:.2f}, "
      f"mass={traj.loc[i, 'mass']:.2f}\n", prim_tbl.round(4).to_string())

# ------------------------------------------------------------------ E. OAT sensitivity
mid = {k: (lo + hi) / 2 for k, (lo, hi) in UNCERTAINTIES.items()}


def peaks(scns):
    """Spike-defining outcome (larger of the egg and chicken peak attributable rise) for a list of scenarios."""
    import vector_sim as vs
    prms = [POLICIES["P0 Baseline"](s) for s in scns]
    dfs = vs.frames(vs.run_batch(prms))
    cfs = vs.frames(vs.run_batch([counterfactual_params(q) for q in prms], columns=CF_COLS))
    out = [compute_outcomes(d, c) for d, c in zip(dfs, cfs)]
    return [max(o["peak_egg_price"], o["peak_chicken_price"]) for o in out]


# Same outcome as the spike classification (max of egg and chicken), so that OAT and SHAP rankings are comparable.
names = list(UNCERTAINTIES)
vals = peaks([mid] + [{**mid, k: UNCERTAINTIES[k][0]} for k in names] + [{**mid, k: UNCERTAINTIES[k][1]} for k in names])
ref, lows, highs = vals[0], vals[1:1 + len(names)], vals[1 + len(names):]
oat = [{"parameter": k, "low": a - ref, "high": b - ref, "swing": abs(b - a)} for k, a, b in zip(names, lows, highs)]
oat = pd.DataFrame(oat).set_index("parameter").sort_values("swing")
save_table(oat, "sd_oat_sensitivity.csv")
fig, ax = plt.subplots(figsize=(8, 6))
ax.barh(oat.index, oat["low"], color="tab:blue", label="Low end of range")
ax.barh(oat.index, oat["high"], color="tab:orange", label="High end of range")
ax.axvline(0, color="k", lw=0.8); ax.legend()
ax.set_xlabel("Change in peak programme-attributable price rise (larger of egg and chicken) vs mid-point")
ax.set_title("One-at-a-time sensitivity (tornado)")
stamp(fig); fig.tight_layout(); fig.savefig(OUT_DIR / "fig_oat_tornado.png", dpi=150); plt.close(fig)
rho = spearmanr(oat["swing"].reindex(imp.index), imp.values).statistic
print(f"\nE. OAT vs SHAP rank correlation (Spearman rho) = {rho:.2f} "
      "(low values = interactions that OAT misses)")

# ------------------------------------------------------------------ F. early warning
Xo = base[OBSERVABLES]
ew_rows = []
for name, m in {"CART (depth 2)": DecisionTreeClassifier(max_depth=2, min_samples_leaf=10, random_state=SEED),
                "Random forest": RandomForestClassifier(500, min_samples_leaf=3, random_state=SEED, n_jobs=-1)}.items():
    s = cross_validate(m, Xo, y, cv=cv, scoring=scoring)
    ew_rows.append({"model": name, **{f"{k}_mean": s[f"test_{k}"].mean() for k in scoring}})
ew = pd.DataFrame(ew_rows).set_index("model")
save_table(ew, "ew_classifier_benchmark.csv")
ew_tree = DecisionTreeClassifier(max_depth=2, min_samples_leaf=10, random_state=SEED).fit(Xo, y)
ew_rules = export_text(ew_tree, feature_names=OBSERVABLES, show_weights=True)
(OUT_DIR / "ew_rules.txt").write_text(ew_rules)
draw_tree(ew_tree, [o.replace("obs_", "").replace("_", " ") + " (week 66)" for o in OBSERVABLES],
          "Early-warning decision tree (indicators 13 weeks after programme start, depth 2)",
          "fig_ew_tree.png", (11, 4.6), precision=3, fontsize=13)
print("\nF. Early-warning classifier (observables at week 65):\n", ew.round(3).to_string(), "\n", ew_rules)
