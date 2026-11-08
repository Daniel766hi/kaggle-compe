# %% [markdown]
# # Who to call with a limited budget: an honest model for the Bank Marketing campaign
#
# The Portuguese bank telemarketing data (Moro et al., 2014) is a classic classification exercise, and
# many notebooks report AUCs above 0.93. Two things inflate those numbers:
#
# 1. **`duration`**, the length of the call, is only known *after* the call (its own documentation says
#    it should be discarded for a realistic model).
# 2. **Random train/test splits**: the campaign ran from May 2008 to November 2010, its success rate rose
#    from 3% to about 50%, and the economic indicators (`euribor3m`, `nr.employed`, ...) change month by
#    month. With a random split, a model can recognise *the month* instead of the customer.
#
# This notebook measures both effects, builds an honest model evaluated on **later months**, and turns it
# into the decisions a campaign manager makes: **how many calls to make, to whom, and when to stop calling
# the same person**.

# %%
import glob
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

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


bank = pd.read_csv(find("bank-additional-full.csv"), sep=";")
bank["y"] = (bank["y"] == "yes").astype(int)
# Rows are in time order (May 2008 to November 2010). Number the months in sequence.
bank["period"] = (bank["month"] != bank["month"].shift()).cumsum()
years = {1: 2008, 8: 2009, 18: 2010}
bank["year"] = pd.Series(bank["period"].map(lambda p: max(y for k, y in years.items() if p >= k)))
bank["label"] = bank["month"].str.capitalize() + " " + bank["year"].astype(str)
print(f"{len(bank):,} calls, {bank['y'].mean():.1%} led to a deposit")

# %% [markdown]
# ## The campaign changed over time

# %%
by_month = bank.groupby("period").agg(month=("label", "first"), calls=("y", "size"), success=("y", "mean"),
                                      euribor=("euribor3m", "mean"))
fig, ax = plt.subplots()
ax.bar(range(len(by_month)), by_month["calls"], color=MUTED, label="calls")
ax2 = ax.twinx()
ax2.plot(range(len(by_month)), 100 * by_month["success"], color=C[7], marker="o", label="success rate (%)")
ax.set_xticks(range(len(by_month)))
ax.set_xticklabels(by_month["month"], rotation=70, fontsize=8)
ax.set_ylabel("calls per month")
ax2.set_ylabel("success rate (%)")
ax2.grid(False)
ax.set_title("Fewer calls, much higher success: the campaign in 2009-2010 was a different campaign")
plt.show()

# %% [markdown]
# ## 1. How much do the two shortcuts inflate the score?

# %%
customer = ["age", "job", "marital", "education", "default", "housing", "loan", "contact", "day_of_week",
            "campaign", "pdays", "previous", "poutcome"]
macro = ["emp.var.rate", "cons.price.idx", "cons.conf.idx", "euribor3m", "nr.employed"]


def frame(cols):
    X = bank[cols].copy()
    for c in X.columns:
        if X[c].dtype == object or str(X[c].dtype) in ("string", "str"):
            X[c] = X[c].astype("category")
    return X


def fit_score(cols, train_idx, test_idx):
    X = frame(cols)
    m = HistGradientBoostingClassifier(categorical_features="from_dtype", max_iter=300, learning_rate=0.05,
                                       random_state=0).fit(X.loc[train_idx], bank.loc[train_idx, "y"])
    p = m.predict_proba(X.loc[test_idx])[:, 1]
    return roc_auc_score(bank.loc[test_idx, "y"], p), m, p


rand_tr, rand_te = train_test_split(bank.index, test_size=0.2, random_state=0, stratify=bank["y"])
cut = int(len(bank) * 0.8)
time_tr, time_te = bank.index[:cut], bank.index[cut:]
rows = []
for label, cols in (("customer + macro + duration", customer + macro + ["duration"]),
                    ("customer + macro", customer + macro), ("macro only (5 numbers per month)", macro),
                    ("customer only", customer)):
    rows.append({"inputs": label, "random split AUC": fit_score(cols, rand_tr, rand_te)[0],
                 "later-months AUC": fit_score(cols, time_tr, time_te)[0]})
pd.DataFrame(rows).round(3)

# %% [markdown]
# - `duration` adds a large, fake gain: you only know how long the call lasted after making it.
# - **Five monthly economic numbers alone** reach a high AUC on a random split, because they identify the
#   month, and months differ hugely in success rate. On later months they score **below 0.5**: the model
#   learned which months went well, and the later months, with interest rates far below anything in the
#   training data, do not follow that pattern.
# - Adding them to customer information makes the later-months score *worse*.
#
# The **honest setup** for a campaign manager is therefore customer information only, trained on earlier
# months and evaluated on later ones.

# %%
auc, model, p_test = fit_score(customer, time_tr, time_te)
test = bank.loc[time_te].assign(p=p_test)
print(f"Test period: {test['label'].iloc[0]} to {test['label'].iloc[-1]}, {len(test):,} calls, "
      f"success rate {test['y'].mean():.1%} (training period: {bank.loc[time_tr, 'y'].mean():.1%})")
print(f"Honest AUC: {auc:.3f}")
calib = test.groupby(pd.qcut(test["p"], 5, duplicates="drop"), observed=True).agg(calls=("y", "size"),
                                                                                    predicted=("p", "mean"), actual=("y", "mean"))
calib.round(3)

# %% [markdown]
# The model **ranks** customers well on later months, but its probabilities are far too low: the base rate
# in the test months is several times the training rate. For a campaign plan, ranking is what matters,
# and the success rate of the plan should be measured, not read off the model.
#
# ## 2. A call budget: how many calls, and to whom?
#
# Rank the test-period customers by the model, call from the top, and count deposits. Compare with calling
# in random order and with a simple rule many banks use: *previous campaign success first, then everyone
# else*.

# %%
order_model = test.sort_values("p", ascending=False)["y"].to_numpy()
order_random = test.sample(frac=1, random_state=0)["y"].to_numpy()
# Rule: previous-campaign successes first, then customers not contacted before, then previous failures;
# random order within each group.
prio = test["poutcome"].map({"success": 0, "nonexistent": 1, "failure": 2})
order_rule = test.assign(prio=prio).sample(frac=1, random_state=1).sort_values("prio", kind="stable")["y"].to_numpy()
share = np.arange(1, len(test) + 1) / len(test)
fig, ax = plt.subplots()
for arr, name, color in ((order_model, "model ranking", C[0]), (order_rule, "previous-success rule", C[3]),
                         (order_random, "random order", MUTED)):
    ax.plot(100 * share, 100 * np.cumsum(arr) / arr.sum(), color=color, label=name)
ax.set_xlabel("% of the customer list called")
ax.set_ylabel("% of all deposits captured")
ax.set_title("Gains: deposits captured as the call list grows (later months)")
ax.legend(loc="lower right")
plt.show()
for pct in (20, 40):
    k = int(len(test) * pct / 100)
    print(f"Calling the top {pct}%: model {order_model[:k].sum() / order_model.sum():.0%}, rule "
          f"{order_rule[:k].sum() / order_rule.sum():.0%}, random {order_random[:k].sum() / order_random.sum():.0%} of deposits")

# %% [markdown]
# ### Profit: where to stop the list
#
# A call costs money (agent time); a deposit brings value (the margin on the deposit over its life). With
# a cost of `CALL_COST` per call and a value of `DEPOSIT_VALUE` per deposit, the profit of calling the top
# *k* customers peaks where the next customer's chance of saying yes falls below `CALL_COST / DEPOSIT_VALUE`.

# %%
CALL_COST, DEPOSIT_VALUE = 8.0, 30.0  # illustrative: break-even at a 27% chance of success
fig, ax = plt.subplots()
best = {}
for arr, name, color in ((order_model, "model ranking", C[0]), (order_rule, "previous-success rule", C[3]),
                         (order_random, "random order", MUTED)):
    profit = DEPOSIT_VALUE * np.cumsum(arr) - CALL_COST * np.arange(1, len(arr) + 1)
    ax.plot(100 * share, profit / 1e3, color=color, label=name)
    best[name] = (profit.max(), 100 * share[profit.argmax()])
ax.set_xlabel("% of the customer list called")
ax.set_ylabel("profit (thousands)")
ax.set_title(f"Profit of the call list (call {CALL_COST:g}, deposit {DEPOSIT_VALUE:g})")
ax.legend()
plt.show()
for name, (pmax, pct) in best.items():
    print(f"{name}: best profit {pmax:,.0f} by calling the top {pct:.0f}%")

# %% [markdown]
# ## 3. When to stop calling the same person
#
# `campaign` is the number of contacts with the customer in this campaign, including the current call:
# it is known before each call. The chance that **the next call** succeeds falls fast:

# %%
fat = bank.assign(calls_so_far=bank["campaign"].clip(upper=10)).groupby("calls_so_far").agg(
    calls=("y", "size"), success=("y", "mean"))
fat["cost per deposit"] = CALL_COST / fat["success"]
fig, ax = plt.subplots()
ax.bar(fat.index, 100 * fat["success"], color=C[0])
ax.axhline(100 * CALL_COST / DEPOSIT_VALUE, color=C[7], ls="--", lw=1)
ax.text(7.2, 100 * CALL_COST / DEPOSIT_VALUE + 0.4, "break-even success rate", color=C[7], fontsize=9)
ax.set_xlabel("contact number in this campaign (10 = 10 or more)")
ax.set_ylabel("success rate of that call (%)")
ax.set_title("Every extra call to the same customer is worth less")
plt.show()
fat.round(3)

# %% [markdown]
# ## Takeaways
#
# - **Drop `duration`** and **split by time**: together they turn a near-perfect score into an honest one.
# - **The economic indicators mostly identify the month**: a random split makes them look powerful, while
#   on later months they hurt. The honest model uses customer information only.
# - **Ranking works on later months even though the success rate shifted**, so a model is useful for
#   deciding whom to call first, while its probabilities need re-calibrating for each new period.
# - **A call budget follows from two numbers** (cost per call, value per deposit): stop where the next
#   customer's success chance falls below their ratio. The same rule says when to stop calling the same
#   customer again.
#
# The cost and value figures are illustrative; change `CALL_COST` and `DEPOSIT_VALUE` to the bank's own.
#
# Data: Moro, Cortez and Rita (2014), *A data-driven approach to predict the success of bank telemarketing*,
# Decision Support Systems 62 (UCI Machine Learning Repository, CC BY 4.0).
