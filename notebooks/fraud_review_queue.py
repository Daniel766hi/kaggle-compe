# %% [markdown]
# # Catching money, not just frauds: a review queue for credit card fraud
#
# On this dataset, 99.8% accuracy means nothing (predicting "no fraud" every time scores 99.83%), and most
# notebooks move to recall, precision or PR-AUC. A fraud team, though, faces a different question:
# **analysts can review only so many alerts per day. Which transactions should they look at?**
#
# This notebook:
# 1. evaluates models on **later hours** (the data covers two days), not a random split;
# 2. ranks alerts two ways, by **fraud probability** and by **expected loss** (probability x amount), and
#    compares the number of frauds and the **euros** caught for the same review effort;
# 3. shows how the popular **undersampling** trick distorts probabilities, why that breaks loss-based
#    ranking, and the one-line correction;
# 4. finds the **review budget** where an extra alert stops paying for the analyst's time.

# %%
import glob
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, roc_auc_score

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


df = pd.read_csv(find("creditcard.csv"))
df["hour"] = df["Time"] / 3600
print(f"{len(df):,} transactions over {df['hour'].max():.0f} hours; {df['Class'].sum()} frauds ({df['Class'].mean():.3%}), "
      f"worth {df.loc[df['Class'] == 1, 'Amount'].sum():,.0f} EUR")

# %% [markdown]
# ## Most frauds are small

# %%
fraud_amounts = df.loc[df["Class"] == 1, "Amount"]
bins = [-0.01, 1, 10, 50, 100, 500, 1000, 30000]
dist = pd.DataFrame({
    "frauds": pd.cut(fraud_amounts, bins).value_counts().sort_index(),
    "share of fraud euros": fraud_amounts.groupby(pd.cut(fraud_amounts, bins), observed=False).sum() / fraud_amounts.sum(),
})
dist["share of frauds"] = dist["frauds"] / dist["frauds"].sum()
dist.round(3)

# %% [markdown]
# Half the frauds are below about 10 EUR (often card testing before a larger theft), while a few hundred-euro
# frauds carry most of the money. A queue that treats every fraud alike spends analyst time on cents.
#
# ## 1. Train on the first hours, test on the last

# %%
features = [f"V{i}" for i in range(1, 29)] + ["Amount", "hour"]
df["hour_of_day"] = df["hour"] % 24
features = [f for f in features if f != "hour"] + ["hour_of_day"]
cut = df["hour"].quantile(0.75)
train, test = df[df["hour"] < cut], df[df["hour"] >= cut].copy()
print(f"train: first {cut:.0f} hours, {len(train):,} transactions ({train['Class'].sum()} frauds); test: last "
      f"{df['hour'].max() - cut:.0f} hours, {len(test):,} ({test['Class'].sum()} frauds, "
      f"{test.loc[test['Class'] == 1, 'Amount'].sum():,.0f} EUR)")

model = HistGradientBoostingClassifier(max_iter=400, learning_rate=0.05, max_leaf_nodes=31, l2_regularization=1.0,
                                       early_stopping=True, validation_fraction=0.15, random_state=0)
model.fit(train[features], train["Class"])
test["p"] = model.predict_proba(test[features])[:, 1]

# The popular alternative: train on a 50/50 undersample of the data.
rng = np.random.default_rng(0)
legit = train[train["Class"] == 0].sample(train["Class"].sum(), random_state=0)
balanced = pd.concat([train[train["Class"] == 1], legit])
under = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, random_state=0).fit(balanced[features], balanced["Class"])
test["p_under"] = under.predict_proba(test[features])[:, 1]
# Prior correction: undersampling multiplied the fraud odds by (legit kept / legit total).
beta = len(legit) / (train["Class"] == 0).sum()
test["p_under_corrected"] = beta * test["p_under"] / (beta * test["p_under"] - test["p_under"] + 1)

rows = []
for col, name in (("p", "full data"), ("p_under", "undersampled 50/50"), ("p_under_corrected", "undersampled, corrected")):
    rows.append({"model": name, "ROC AUC": roc_auc_score(test["Class"], test[col]),
                 "PR AUC": average_precision_score(test["Class"], test[col]),
                 "mean predicted fraud rate": test[col].mean(), "actual fraud rate": test["Class"].mean()})
print(f"The undersampled model predicts a fraud rate {test['p_under'].mean() / test['Class'].mean():.0f} times the actual one.")
pd.DataFrame(rows).round(4)

# %% [markdown]
# The undersampled model ranks about as well as the full one, but its probabilities are inflated by a
# factor of tens. The correction `p' = beta p / (beta p - p + 1)`, with `beta` the share of
# legitimate transactions kept, brings them back to scale. That matters as soon as probabilities are
# multiplied by amounts.
#
# ## 2. The review queue: probability or expected loss?
#
# Analysts review the top *k* alerts of the test period. Ranking by probability catches the most frauds;
# ranking by **expected loss = probability x amount** should catch the most euros.

# %%
def caught(order_col, k):
    top = test.nlargest(k, order_col)
    fr = top[top["Class"] == 1]
    return len(fr), fr["Amount"].sum()


test["exp_loss"] = test["p"] * test["Amount"]
test["exp_loss_under"] = test["p_under"] * test["Amount"]
test["exp_loss_under_corr"] = test["p_under_corrected"] * test["Amount"]
total_frauds, total_eur = test["Class"].sum(), test.loc[test["Class"] == 1, "Amount"].sum()
ks = [25, 50, 100, 200, 300, 500, 1000]
rows = []
for k in ks:
    row = {"alerts reviewed": k}
    for col, name in (("p", "by probability"), ("exp_loss", "by expected loss"),
                      ("exp_loss_under", "expected loss, undersampled"),
                      ("exp_loss_under_corr", "expected loss, undersampled corrected")):
        n, eur = caught(col, k)
        row[f"{name}: frauds"] = n
        row[f"{name}: EUR"] = eur
    rows.append(row)
queue = pd.DataFrame(rows)

fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))
for name, color in (("by probability", C[0]), ("by expected loss", C[7]), ("expected loss, undersampled", MUTED),
                    ("expected loss, undersampled corrected", C[3])):
    axes[0].plot(queue["alerts reviewed"], 100 * queue[f"{name}: frauds"] / total_frauds, marker="o", color=color, label=name)
    axes[1].plot(queue["alerts reviewed"], 100 * queue[f"{name}: EUR"] / total_eur, marker="o", color=color, label=name)
axes[0].set_title("% of frauds caught")
axes[1].set_title("% of fraud euros caught")
for ax in axes:
    ax.set_xscale("log")
    ax.set_xlabel("alerts reviewed in the test period")
axes[1].legend(fontsize=8.5)
plt.tight_layout()
plt.show()
queue[["alerts reviewed", "by probability: frauds", "by probability: EUR", "by expected loss: frauds",
       "by expected loss: EUR"]].round(0)

# %% [markdown]
# When analysts can only look at a few dozen alerts, ranking by expected loss catches **fewer frauds but
# clearly more money** (about a third more in the first 25 to 50 alerts), because it skips the many tiny
# card-testing charges. Once the queue is long enough to cover nearly all likely frauds (100 alerts and
# more here), both rankings converge. The **uncorrected undersampled** model is by far the worst at
# catching money: its inflated probabilities make small transactions look as dangerous as large ones, so
# its first 50 alerts stop no fraud euros at all.
#
# ## 3. How many alerts are worth reviewing?
#
# With a cost of `REVIEW_COST` per alert, the next alert is worth reviewing while its expected loss is
# above that cost. Net savings as the queue grows:

# %%
REVIEW_COST = 5.0  # EUR of analyst time per alert (illustrative)
order = test.sort_values("exp_loss", ascending=False)
saved = np.cumsum(np.where(order["Class"] == 1, order["Amount"], 0)) - REVIEW_COST * np.arange(1, len(order) + 1)
k_best = int(saved[:5000].argmax()) + 1
fig, ax = plt.subplots()
ax.plot(np.arange(1, 5001), saved[:5000], color=C[0])
ax.axvline(k_best, color=C[7], ls="--", lw=1)
ax.set_xlabel("alerts reviewed (ranked by expected loss)")
ax.set_ylabel("fraud euros stopped minus review cost")
ax.set_title(f"Net savings peak at about {k_best} alerts in the test period")
plt.show()
hours = test["hour"].max() - test["hour"].min()
k_rule = int((order["exp_loss"] > REVIEW_COST).sum())  # the rule: review while expected loss > review cost
for label, k in (("Rule (expected loss above the review cost)", k_rule), ("Best in hindsight", k_best)):
    stopped = order["Amount"].iloc[:k][order["Class"].iloc[:k] == 1].sum()
    print(f"{label}: {k} alerts over {hours:.0f} hours ({k / hours:.0f} per hour), stopping {stopped:,.0f} of "
          f"{total_eur:,.0f} fraud EUR for {REVIEW_COST * k:,.0f} EUR of review time (net {stopped - REVIEW_COST * k:,.0f})")

# %% [markdown]
# The rule, decided in advance from the model's expected losses, lands close to the best queue in hindsight;
# the realized curve is jumpy because a single large fraud ranked lower can move the peak.

# %% [markdown]
# ## Takeaways
#
# - **Evaluate on later hours**, not a random split, and judge models by what a fraud team can act on.
# - **Rank alerts by expected loss**, not probability alone, when capacity is tight: the first few dozen
#   reviews stop about a third more money, at the price of letting tiny card-testing charges through (which
#   a separate rule can catch).
# - **If you undersample, correct the probabilities.** Without the correction, any cost-based decision built
#   on them is distorted.
# - **The size of the queue is an economic decision**: review while the expected loss of the next alert
#   exceeds the cost of reviewing it.
#
# Caveats: amounts are the only money field (no chargeback or recovery data), reviewing an alert is assumed
# to stop the fraud, and the review cost is illustrative.
#
# Data: Worldline and the Machine Learning Group of ULB (Dal Pozzolo et al., 2015), Credit Card Fraud
# Detection (Open Database License).
