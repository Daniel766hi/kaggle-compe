# %% [markdown]
# # 98% accuracy is a leak: a forensic audit of the DataCo supply chain dataset
#
# DataCo is one of Kaggle's most used supply chain datasets, and the most common task on it is
# predicting **late delivery** (`Late_delivery_risk`). Many notebooks report 97-99% accuracy. This
# notebook shows why those numbers cannot be real, what an honest model can achieve, and what the data
# itself reveals about how it was made, so that you can use it for what it is good for.
#
# 1. **The label is a formula.** `Late_delivery_risk` is exactly *real shipping days > scheduled days*,
#    and three common feature columns contain the answer.
# 2. **Leaky vs honest models.** The same model with and without the leaked columns, evaluated on later
#    orders.
# 3. **The fingerprints of a simulation.** Shipping times follow a fixed dice-roll pattern per shipping
#    mode, unrelated to distance, market, product, season or volume.
# 4. **What is left to learn**, and a decision that uses it: which shipping mode to offer.

# %%
import glob
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import accuracy_score, roc_auc_score

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


df = pd.read_csv(find("DataCoSupplyChainDataset.csv"), encoding="latin-1")
df["order_date"] = pd.to_datetime(df["order date (DateOrders)"])
df["ship_date"] = pd.to_datetime(df["shipping date (DateOrders)"])
real, sched = df["Days for shipping (real)"], df["Days for shipment (scheduled)"]
print(f"{len(df):,} order lines, {df['Order Id'].nunique():,} orders, {df['order_date'].min():%b %Y} to {df['order_date'].max():%b %Y}")
print(f"Late_delivery_risk = 1 for {df['Late_delivery_risk'].mean():.1%} of lines")

# %% [markdown]
# ## 1. The label is a formula
#
# If `Late_delivery_risk` is "shipped later than scheduled", it should equal `real > scheduled` on every
# non-cancelled line.

# %%
active = df["Delivery Status"] != "Shipping canceled"
rule = (real > sched).astype(int)
print(f"Late_delivery_risk == (real days > scheduled days): {(rule[active] == df.loc[active, 'Late_delivery_risk']).mean():.2%} "
      f"of non-cancelled lines")
print(f"Cancelled lines: {(~active).sum():,}, all labelled 0 whatever their dates")
pd.crosstab(df["Delivery Status"], df["Late_delivery_risk"])

# %% [markdown]
# The label is fully determined by columns that are only known **after** shipping:
#
# | Column | Why it leaks |
# |---|---|
# | `Delivery Status` | "Late delivery" is the label itself, word for word |
# | `Days for shipping (real)` | with the scheduled days, it *is* the label |
# | `shipping date (DateOrders)` | shipping date minus order date gives the real shipping days |
# | `Order Status` | partly recorded after shipping (e.g. complete, closed) |
#
# A model fed any of these is not predicting anything: it is recomputing the formula.
#
# ## 2. Leaky vs honest
#
# Same algorithm, three sets of inputs, trained on the first 80% of orders by date and tested on the
# last 20%:
# - **leaky**: everything, including the four columns above (what most notebooks do);
# - **honest**: only what is known when the order is placed;
# - **shipping mode only**: the late rate of each mode, as a lookup table.

# %%
df = df[active].sort_values("order_date").reset_index(drop=True)
df["ship_days_from_dates"] = (df["ship_date"] - df["order_date"]).dt.days
df["weekday"] = df["order_date"].dt.weekday
df["month"] = df["order_date"].dt.month
df["hour"] = df["order_date"].dt.hour
order_time = ["Shipping Mode", "Days for shipment (scheduled)", "Market", "Order Region", "Order Country",
              "Category Name", "Department Name", "Customer Segment", "Type", "Order Item Quantity",
              "Order Item Product Price", "Order Item Discount Rate", "Sales", "weekday", "month", "hour"]
leaks = ["Delivery Status", "Days for shipping (real)", "ship_days_from_dates", "Order Status"]
y = df["Late_delivery_risk"]
cut = df["order_date"].quantile(0.8)
tr, te = df["order_date"] < cut, df["order_date"] >= cut


def frame(cols):
    X = df[cols].copy()
    for c in X.columns:
        if X[c].dtype == object or str(X[c].dtype) in ("string", "str"):
            X[c] = X[c].astype("category")
    return X


results, models = [], {}
for name, cols in (("leaky", order_time + leaks), ("honest", order_time)):
    X = frame(cols)
    m = HistGradientBoostingClassifier(categorical_features="from_dtype", max_iter=300, random_state=0)
    m.fit(X[tr], y[tr])
    p = m.predict_proba(X[te])[:, 1]
    models[name] = (m, X)
    results.append({"model": name, "accuracy": accuracy_score(y[te], p > 0.5), "ROC AUC": roc_auc_score(y[te], p)})
mode_rate = df[tr].groupby("Shipping Mode")["Late_delivery_risk"].mean()
p_mode = df.loc[te, "Shipping Mode"].map(mode_rate)
results.append({"model": "shipping mode only", "accuracy": accuracy_score(y[te], p_mode > 0.5),
                "ROC AUC": roc_auc_score(y[te], p_mode)})
results.append({"model": "always predict 'late'", "accuracy": y[te].mean(), "ROC AUC": 0.5})
pd.DataFrame(results).round(4)

# %% [markdown]
# The leaky model is near perfect because it is computing the label. Without the leaks, accuracy falls
# to about the level of a lookup table on the shipping mode. Which order-time inputs does the honest
# model actually use?

# %%
m, X = models["honest"]
sample = X[te].sample(8000, random_state=0)
imp = permutation_importance(m, sample, y.loc[sample.index], scoring="roc_auc", n_repeats=3, random_state=0)
pd.Series(imp.importances_mean, index=sample.columns).sort_values(ascending=False).round(4).head(10) \
    .rename("drop in AUC when shuffled").to_frame()

# %% [markdown]
# Shipping mode carries nearly all the signal. The only other input that matters is the **hour** the
# order was placed, and only for one mode:

# %%
orders = df.drop_duplicates("Order Id").copy()
by_hour = orders.groupby(["Shipping Mode", orders["hour"] // 3 * 3])["Late_delivery_risk"].mean().unstack().round(2)
by_hour.columns = [f"{h:02d}-{h + 2:02d}h" for h in by_hour.columns]
by_hour

# %% [markdown]
# Same Day orders placed before noon are **never** late and those placed after noon are **always** late:
# a hard-coded rule, not a pattern of real operations.
#
# ## 3. Fingerprints of a simulation
#
# In a real logistics network, shipping time depends on distance, destination, carrier load, season and
# order size. Here is the distribution of real shipping days within each shipping mode:

# %%
dist = pd.crosstab(df["Shipping Mode"], df["Days for shipping (real)"], normalize="index")
fig, ax = plt.subplots()
modes = ["Same Day", "First Class", "Second Class", "Standard Class"]
width = 0.2
for i, mode in enumerate(modes):
    ax.bar(dist.columns + (i - 1.5) * width, dist.loc[mode] * 100, width=width, color=C[i], label=mode)
ax.set_xlabel("real shipping days")
ax.set_ylabel("% of the mode's orders")
ax.set_title("Each mode draws its shipping time from a fixed, flat distribution")
ax.legend()
plt.show()
dist.round(3)

# %% [markdown]
# - **First Class always takes exactly 2 days** while it is scheduled for 1, so it is "late" by
#   construction.
# - **Second and Standard Class are uniform** over 2 to 6 days: each value about 20%.
# - **Same Day is 0 or 1 day**, half and half.
#
# A chi-square test of independence checks whether, within a mode, shipping days depend on anything. The
# test uses one row per **order** (all lines of an order share its shipping time, so counting lines would
# overstate the evidence).

# %%
rows = []
for mode in ["Standard Class", "Second Class"]:
    sub = orders[orders["Shipping Mode"] == mode]
    for col in ["Market", "Order Region", "Category Name", "Customer Segment", "Type", "month", "weekday"]:
        table = pd.crosstab(sub[col], sub["Days for shipping (real)"])
        table = table[table.sum(axis=1) >= 50]
        chi2, pval, dof, _ = stats.chi2_contingency(table)
        cramers_v = np.sqrt(chi2 / (table.to_numpy().sum() * (min(table.shape) - 1)))
        rows.append({"mode": mode, "shipping days vs": col, "Cramer's V": round(cramers_v, 4), "p-value": round(pval, 3)})
    rho = stats.spearmanr(sub["Order Item Quantity"], sub["Days for shipping (real)"])
    rows.append({"mode": mode, "shipping days vs": "quantity (Spearman)", "Cramer's V": round(abs(rho.statistic), 4),
                 "p-value": round(rho.pvalue, 3)})
pd.DataFrame(rows)

# %% [markdown]
# Association strengths are essentially zero (Cramer's V of a few hundredths at most, where a real
# dependence would show tenths): shipping time does not depend on where the order goes, what it contains,
# who buys it, or when, and none of the tests is significant. Shipping time across the five markets,
# from Europe to Africa, is the same:

# %%
by_market = df[df["Shipping Mode"] == "Standard Class"].groupby("Market")["Days for shipping (real)"].agg(["mean", "std", "size"])
by_market.round(3)

# %% [markdown]
# Two more fingerprints:

# %%
same_minute = (orders["ship_date"].dt.minute == orders["order_date"].dt.minute).mean()
per_day = orders.groupby(orders["order_date"].dt.date).size()
print(f"Shipping timestamp has the same minute as the order timestamp: {same_minute:.1%} of orders")
print(f"Orders per day: mean {per_day.mean():.1f}, standard deviation {per_day.std():.1f}, "
      f"min {per_day.min()}, max {per_day.max()} (no weekends, holidays or seasons)")
weekday = orders.groupby(orders["order_date"].dt.day_name())["Order Id"].size()
print("Orders by weekday:", weekday.to_dict())

# %% [markdown]
# Shipping times are whole numbers of days added to the order time, and almost the same number of
# orders arrives every day of the week, all year. Together these are strong evidence that the delivery
# fields were **generated**: each order's shipping
# time is drawn at random from a distribution that depends only on its shipping mode. That does not make
# the dataset useless, but it changes what it can teach.
#
# ## 4. What is left to learn: choosing a shipping mode
#
# Since lateness depends only on the mode, the useful model is a table: for each mode, the distribution
# of shipping days. A business decision that uses it: **which promise to show the customer** so that
# a target share of orders arrives on time.

# %%
summary = df.groupby("Shipping Mode").agg(orders=("Order Id", "nunique"), scheduled=("Days for shipment (scheduled)", "first"),
                                          late_rate=("Late_delivery_risk", "mean"),
                                          avg_days=("Days for shipping (real)", "mean"))
for target in (0.80, 0.95):
    summary[f"days to promise for {target:.0%} on time"] = df.groupby("Shipping Mode")["Days for shipping (real)"].quantile(target)
summary.loc[modes].round(3)

# %% [markdown]
# Under this data, DataCo's scheduled days are too optimistic for every mode except Standard Class: an
# honest promise would be 2 days for First Class and 6 days for Second and Standard Class to keep 95% of
# orders on time.
#
# ## Takeaways
#
# - **Check what the label is made of.** `Late_delivery_risk` is a formula of two columns; any feature
#   computed after shipping (`Delivery Status`, real shipping days, shipping date, `Order Status`) leaks it.
# - **Honest late-delivery prediction on DataCo tops out around the shipping-mode baseline**, not 98%.
# - **The delivery data is simulated**: flat, fixed distributions per mode, independent of geography,
#   product and time; a noon rule for Same Day; whole-day shipping times; a constant flow of orders. Use the dataset for what it supports (sales, profit, customer and product analysis,
#   SQL and dashboard practice, leakage teaching), and do not draw logistics conclusions from its delivery
#   times.
#
# Data: DataCo Smart Supply Chain for Big Data Analysis (Constante, Silva and Pereira, Mendeley Data,
# 2019; CC0 on Kaggle).
