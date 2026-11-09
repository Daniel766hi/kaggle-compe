# %% [markdown]
# # Who is worth saving? Customer lifetime and value-based retention for Telco churn
#
# The usual churn notebook ends with a classifier and its AUC. A retention team needs to know something
# else: **which customers to spend a retention offer on**. The riskiest customers are not always the most
# valuable to save: a brand-new customer on a cheap plan is likely to leave, but losing them costs little.
#
# This notebook:
# 1. measures **churn hazard by month of tenure** for each contract type (when do customers leave?);
# 2. turns it into each customer's **expected remaining lifetime and value**;
# 3. builds a churn model on customer attributes, validated out of sample;
# 4. compares targeting retention offers **by churn probability** with targeting **by expected value saved**,
#    for the same number of offers.

# %%
import glob
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict

INK, INK2, GRID, SURFACE, MUTED = "#0b0b0b", "#52514e", "#e6e5e0", "#fcfcfb", "#c3c2b7"
C = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
    "axes.titlesize": 13, "axes.titleweight": "bold", "axes.titlecolor": INK, "axes.titlelocation": "left",
    "font.size": 10.5, "lines.linewidth": 2, "figure.figsize": (11, 4.6), "figure.dpi": 110,
    "legend.frameon": False, "axes.xmargin": 0.01,
})


def find(name):
    for root in ("/kaggle/input", os.environ.get("DATA_ROOT", "../input")):
        hits = glob.glob(f"{root}/**/{name}", recursive=True)
        if hits:
            return hits[0]
    raise FileNotFoundError(name)


t = pd.read_csv(find("WA_Fn-UseC_-Telco-Customer-Churn.csv"))
t["churn"] = (t["Churn"] == "Yes").astype(int)
t["TotalCharges"] = pd.to_numeric(t["TotalCharges"], errors="coerce").fillna(0)  # blank for brand-new customers
print(f"{len(t):,} customers, {t['churn'].mean():.1%} churned in the last month; "
      f"tenure 0-{t['tenure'].max()} months")
t.groupby("Contract")["churn"].agg(["mean", "size"]).rename(columns={"mean": "churn rate", "size": "customers"}).round(3)

# %% [markdown]
# ## 1. When do customers leave?
#
# This is survival data: a customer who churned has a complete lifetime (their tenure), and a customer who
# is still here has a lifetime of *at least* their tenure (it is censored). The Kaplan-Meier estimate of the
# monthly **churn hazard** at month *t* is the number who left at month *t* divided by everyone still a
# customer at month *t*, that is with tenure of at least *t*. (It assumes customers who joined in different
# years behave alike; a snapshot cannot do better.)

# %%
def hazard(df, max_t=72):
    months = range(max_t + 1)
    at_risk = pd.Series([(df["tenure"] >= m).sum() for m in months], index=months)
    left = df[df["churn"] == 1].groupby("tenure").size().reindex(months, fill_value=0)
    # Smooth with a centred 5-month window (weighted by customers at risk) so single months do not jump.
    smooth = left.rolling(5, center=True, min_periods=1).sum() / at_risk.rolling(5, center=True, min_periods=1).sum()
    return smooth.fillna(0)


contracts = ["Month-to-month", "One year", "Two year"]
H = {c: hazard(t[t["Contract"] == c]) for c in contracts}
fig, ax = plt.subplots()
for c, color in zip(contracts, [C[7], C[3], C[0]]):
    ax.plot(H[c].index[1:], 100 * H[c].iloc[1:], color=color, label=c)
ax.set_xlabel("tenure (months)")
ax.set_ylabel("monthly churn hazard (%)")
ax.set_title("Churn hazard by tenure: month-to-month customers leave early; contracts lock customers in")
ax.legend()
plt.show()
print({c: f"month 1: {100 * H[c].iloc[1]:.1f}%, month 12: {100 * H[c].iloc[12]:.1f}%, month 36: {100 * H[c].iloc[36]:.1f}%"
       for c in contracts})

# %% [markdown]
# The hazard is highest in the first months on month-to-month plans, then settles around 1.5-2% a month.
# The rise after about 60 months should be read with care: few customers have been around that long (tenure
# stops at 72 months in this data), so those estimates rest on small numbers.
#
# ## 2. Expected remaining lifetime and value
#
# From the hazard curve, a customer at tenure *t* stays another month with probability `1 - h(t)`, and so
# on. The expected number of remaining months (capped at 6 years) times the monthly margin gives the
# customer's **expected remaining value**. We assume a 40% margin on monthly charges and a 1% monthly
# discount rate; both are parameters.

# %%
MARGIN, MONTHLY_DISCOUNT, HORIZON = 0.40, 0.01, 72


def remaining_months(h, tenure, horizon=HORIZON):
    """Expected discounted months still to come for a customer currently at `tenure` (after this month)."""
    alive, total = 1.0, 0.0
    for k in range(1, horizon + 1):
        alive *= 1 - h.iloc[min(tenure + k, len(h) - 1)]
        total += alive / (1 + MONTHLY_DISCOUNT) ** k
    return total


lookup = {(c, ten): remaining_months(H[c], ten) for c in contracts for ten in range(73)}
t["remaining_months"] = [lookup[(c, ten)] for c, ten in zip(t["Contract"], t["tenure"])]
t["value_if_stays"] = t["MonthlyCharges"] * MARGIN * t["remaining_months"]
t.groupby("Contract")[["remaining_months", "value_if_stays"]].median().round(1)

# %% [markdown]
# ## 3. Who is likely to leave? An out-of-sample churn model
#
# Customer attributes only (services, contract, billing, charges, tenure). Probabilities come from 5-fold
# cross-validation, so every customer is scored by a model that never saw them.

# %%
features = [c for c in t.columns if c not in ("customerID", "Churn", "churn", "remaining_months", "value_if_stays")]
X = t[features].copy()
for c in X.columns:
    if X[c].dtype == object or str(X[c].dtype) in ("string", "str"):
        X[c] = X[c].astype("category")
model = HistGradientBoostingClassifier(categorical_features="from_dtype", max_iter=200, learning_rate=0.05,
                                       max_leaf_nodes=15, random_state=0)
t["p_churn"] = cross_val_predict(model, X, t["churn"], cv=StratifiedKFold(5, shuffle=True, random_state=0),
                                 method="predict_proba")[:, 1]
print(f"Out-of-sample ROC AUC: {roc_auc_score(t['churn'], t['p_churn']):.3f}")

# %% [markdown]
# ## 4. Targeting: probability or value?
#
# A retention offer (say a discount or an upgrade worth `OFFER_COST`) keeps a would-be churner with
# probability `SAVE_RATE`. The expected value of making the offer to customer *i* is
#
# `p_churn(i) x SAVE_RATE x value_if_stays(i) - OFFER_COST`.
#
# We compare two ways of choosing who gets the offers: the highest **churn probability** first, or the
# highest **expected value** first, and count the value actually saved among customers who really churned
# (each churner reached with an offer is saved with probability `SAVE_RATE`).

# %%
OFFER_COST, SAVE_RATE = 30.0, 0.30
t["offer_value"] = t["p_churn"] * SAVE_RATE * t["value_if_stays"] - OFFER_COST
realized = t["churn"] * SAVE_RATE * t["value_if_stays"]  # expected value saved if this customer gets an offer
ks = np.arange(250, len(t) + 1, 250)
rows = []
for k in ks:
    by_p = t.nlargest(k, "p_churn")
    by_v = t.nlargest(k, "offer_value")
    rows.append({"offers": k,
                 "by probability: churners reached": by_p["churn"].sum(),
                 "by probability: net value": realized[by_p.index].sum() - OFFER_COST * k,
                 "by value: churners reached": by_v["churn"].sum(),
                 "by value: net value": realized[by_v.index].sum() - OFFER_COST * k})
tgt = pd.DataFrame(rows)
fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))
axes[0].plot(tgt["offers"], tgt["by probability: churners reached"], color=C[7], label="by churn probability")
axes[0].plot(tgt["offers"], tgt["by value: churners reached"], color=C[0], label="by expected value")
axes[0].set_title("Churners reached")
axes[1].plot(tgt["offers"], tgt["by probability: net value"] / 1e3, color=C[7], label="by churn probability")
axes[1].plot(tgt["offers"], tgt["by value: net value"] / 1e3, color=C[0], label="by expected value")
axes[1].set_title("Net value saved (thousands)")
for ax in axes:
    ax.set_xlabel("number of retention offers")
    ax.legend()
plt.tight_layout()
plt.show()
best_p = tgt.loc[tgt["by probability: net value"].idxmax()]
best_v = tgt.loc[tgt["by value: net value"].idxmax()]
print(f"Best by probability: {best_p['by probability: net value']:,.0f} with {int(best_p['offers'])} offers")
print(f"Best by value:       {best_v['by value: net value']:,.0f} with {int(best_v['offers'])} offers")
fixed = tgt[tgt["offers"].isin([500, 1000, 2000])].set_index("offers")
fixed["gain of value ranking %"] = 100 * (fixed["by value: net value"] / fixed["by probability: net value"] - 1)
fixed.round(0)

# %% [markdown]
# Ranking by expected value saves more at every budget, by 3% to 12% here, and reaches its best result with
# fewer offers. The gain is modest:
# churn risk and customer value are not strongly opposed in this data, because high-risk customers also tend
# to pay high monthly charges (fiber plans). The gap would be larger where the riskiest customers are the
# cheapest ones.
#
# Who are the customers each ranking picks first?

# %%
k = 500
profile = pd.DataFrame({
    "by probability": t.nlargest(k, "p_churn")[["tenure", "MonthlyCharges", "p_churn", "value_if_stays"]].median(),
    "by value": t.nlargest(k, "offer_value")[["tenure", "MonthlyCharges", "p_churn", "value_if_stays"]].median(),
    "all customers": t[["tenure", "MonthlyCharges", "p_churn", "value_if_stays"]].median(),
}).round(2)
profile

# %% [markdown]
# ## Takeaways
#
# - **Churn is front-loaded on month-to-month plans**: the hazard is highest in the first months and falls
#   with tenure; one- and two-year contracts lock customers in.
# - **Value at risk is not the same as risk.** Combining the churn model with the hazard-based lifetime gives
#   each customer an expected value of saving; ranking by it beats ranking by churn probability for every
#   budget, by 3-12% here; modest, because risky customers are also high payers.
# - **The budget size follows from the economics**: make offers while the expected value of the next one is
#   positive.
#
# Assumptions: hazard from a single snapshot (stable customer base), 40% margin, 1% monthly discount rate,
# offer cost 30, save rate 30%. These are illustrative and should be replaced by the operator's own figures.
#
# Data: IBM sample data set, Telco Customer Churn (shared on Kaggle by BlastChar).
