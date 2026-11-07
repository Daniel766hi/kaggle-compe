# %% [markdown]
# # The promise cliff: delivery dates, reviews, and how to set a better promise (Olist)
#
# Almost every notebook on this dataset shows that late orders get bad reviews. This one asks the
# questions that matter for running a marketplace's logistics:
#
# 1. **Is it speed or the promise?** Reviews barely care *how early* an order arrives, but start falling
#    the day it misses its promised date, and keep falling with every extra day. We measure that bend
#    with a **regression kink design**, check it with controls and placebo dates, and compare orders
#    with the *same* delivery time but different promises.
# 2. **How much is a day worth?** Being early earns almost nothing; being late costs a lot. That
#    asymmetry decides how a promise should be set.
# 3. **Why are promises so long, and can they be shorter?** Olist promised **24 days on average** for
#    deliveries that took **12**. We train **quantile models** on what is known at checkout, trace the
#    trade-off between promise length and lateness, and find where the long promises come from.
#
# Everything is evaluated on the most recent orders, with models trained only on earlier ones.

# %%
import glob
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LinearRegression

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


def read(name, **kw):
    return pd.read_csv(find(f"olist_{name}_dataset.csv"), **kw)


# %% [markdown]
# ## Data: one row per delivered order with a review
#
# `margin` = promised date minus delivery date, in days: positive = early, negative = late.

# %%
ts = ["order_purchase_timestamp", "order_delivered_customer_date", "order_estimated_delivery_date"]
orders = read("orders", parse_dates=ts)
reviews = read("order_reviews", parse_dates=["review_creation_date"])
items = read("order_items")
products = read("products")
customers = read("customers")
sellers = read("sellers")
geo = read("geolocation").groupby("geolocation_zip_code_prefix")[["geolocation_lat", "geolocation_lng"]].mean()
cats = pd.read_csv(find("product_category_name_translation.csv"))

reviews = reviews.sort_values("review_creation_date").drop_duplicates("order_id", keep="last")
o = orders[(orders["order_status"] == "delivered") & orders["order_delivered_customer_date"].notna()].copy()
o = o.merge(reviews[["order_id", "review_score", "review_creation_date"]], on="order_id", how="inner")
o["margin"] = (o["order_estimated_delivery_date"].dt.normalize() - o["order_delivered_customer_date"].dt.normalize()).dt.days
o["late"] = (o["margin"] < 0).astype(int)
o["promise_days"] = (o["order_estimated_delivery_date"].dt.normalize() - o["order_purchase_timestamp"].dt.normalize()).dt.days
o["actual_days"] = (o["order_delivered_customer_date"] - o["order_purchase_timestamp"]).dt.total_seconds() / 86400

# Order-level features known at checkout.
first_item = items.sort_values("order_item_id").drop_duplicates("order_id")
agg = items.groupby("order_id").agg(n_items=("order_item_id", "size"), price=("price", "sum"),
                                    freight=("freight_value", "sum"), n_sellers=("seller_id", "nunique"))
prod = products.merge(cats, on="product_category_name", how="left")
prod["volume_cm3"] = prod["product_length_cm"] * prod["product_height_cm"] * prod["product_width_cm"]
o = (o.merge(agg, on="order_id")
      .merge(first_item[["order_id", "seller_id", "product_id"]], on="order_id")
      .merge(prod[["product_id", "product_category_name_english", "product_weight_g", "volume_cm3"]], on="product_id", how="left")
      .merge(customers[["customer_id", "customer_zip_code_prefix", "customer_state"]], on="customer_id")
      .merge(sellers[["seller_id", "seller_zip_code_prefix", "seller_state"]], on="seller_id"))
c_ll = geo.reindex(o["customer_zip_code_prefix"]).to_numpy()
s_ll = geo.reindex(o["seller_zip_code_prefix"]).to_numpy()
lat1, lon1, lat2, lon2 = map(np.radians, (c_ll[:, 0], c_ll[:, 1], s_ll[:, 0], s_ll[:, 1]))
o["distance_km"] = 6371 * 2 * np.arcsin(np.sqrt(np.sin((lat2 - lat1) / 2) ** 2
                                               + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2))
o["category"] = o["product_category_name_english"].fillna("unknown")
print(f"{len(o):,} delivered orders with a review, {o['order_purchase_timestamp'].min():%b %Y} to "
      f"{o['order_purchase_timestamp'].max():%b %Y}")
print(f"Late: {o['late'].mean():.1%}. Average promise {o['promise_days'].mean():.1f} days; "
      f"average delivery {o['actual_days'].mean():.1f} days.")

# %% [markdown]
# ## 1. The cliff
#
# Average review score and share of 1-star reviews by how early (right) or late (left) the order arrived.

# %%
win = o[o["margin"].between(-15, 20)]
curve = win.groupby("margin").agg(orders=("review_score", "size"), score=("review_score", "mean"),
                                  one_star=("review_score", lambda s: (s == 1).mean()))
fig, ax = plt.subplots()
ax.bar(curve.index, curve["score"], color=np.where(curve.index < 0, C[7], C[0]), width=0.8)
ax.axvline(-0.5, color=INK, lw=1, ls="--")
ax.text(-0.3, 4.6, "promised date", fontsize=9.5)
ax.set_ylim(1, 5)
ax.set_xlabel("days early (+) or late (-) versus the promised date")
ax.set_ylabel("average review score")
ax.set_title("Reviews hardly reward earliness, and collapse right after the promise")
plt.show()
print(curve.loc[[-5, -3, -2, -1, 0, 1, 5, 10, 15]].round(3).to_string())

# %% [markdown]
# ## 2. Is the cliff causal? A regression kink design
#
# The curve does not jump at the promised date: it **bends**. While an order is early, reviews hardly
# change; once it is late, they fall with every day. So we estimate the **change in slope** at the
# promised date (a regression kink design): on a window of days around a cutoff, fit
# `score = a + b * days + k * days * (cutoff missed)` and read off `k`, the extra stars lost per day
# beyond the cutoff. We add controls (product category, customer and seller state, price, freight,
# distance, month) and run **placebo cutoffs** on days where nothing special happens, with windows that
# stay entirely on the early side or entirely on the late side.

# %%
def kink(df, cutoff=0, h=5, controls=False, boots=300):
    w = df[df["margin"].between(cutoff - h, cutoff + h)].copy()
    x = (w["margin"] - cutoff).astype(float)
    X = pd.DataFrame({"x": x, "x_beyond": x * (x < 0)}, index=w.index)
    if controls:
        dummies = pd.get_dummies(w[["category", "customer_state", "seller_state"]].astype(str), drop_first=True)
        num = w[["price", "freight", "distance_km"]].fillna(w[["price", "freight", "distance_km"]].median())
        month = pd.get_dummies(w["order_purchase_timestamp"].dt.to_period("M").astype(str), drop_first=True)
        X = pd.concat([X, np.log1p(num), dummies, month], axis=1)
    Xv, y = X.to_numpy(float), w["review_score"].to_numpy(float)
    k = LinearRegression().fit(Xv, y).coef_[1]
    rng = np.random.default_rng(0)
    draws = [LinearRegression().fit(Xv[i], y[i]).coef_[1] for i in (rng.integers(0, len(y), len(y)) for _ in range(boots))]
    return k, np.std(draws), len(w)


rows = []
for label, kwargs in [("at the promised date", {}), ("at the promised date, with controls", {"controls": True}),
                      ("at the promised date, window 3 days", {"h": 3}),
                      ("placebo: 7 days early (window all early)", {"cutoff": 7, "h": 5}),
                      ("placebo: 13 days early (window all early)", {"cutoff": 13, "h": 5}),
                      ("placebo: 7 days late (window all late)", {"cutoff": -7, "h": 5})]:
    k, se, n = kink(o, **kwargs)
    rows.append({"cutoff": label, "extra stars lost per day beyond it": round(k, 3), "std error": round(se, 3),
                 "orders": n})
kink_table = pd.DataFrame(rows)
kink_table

# %% [markdown]
# At the promised date, each day beyond it costs about **0.35 to 0.45 stars more** than the trend before
# it, with or without controls. At the early-side placebo dates the slope barely changes (about 0.01 to
# 0.02). At the late-side placebo the slope *eases* (negative value): once reviews approach the 1-star
# floor they cannot fall much further. The bend sits exactly at the promise.
#
# ## 3. Same speed, different promise
#
# The strongest check: compare orders that took **the same number of days**, some of which beat their
# promise and some of which missed it.

# %%
o["actual_day_bin"] = o["actual_days"].round()
same = o[o["actual_day_bin"].between(8, 25)].groupby(["actual_day_bin", "late"])["review_score"].mean().unstack()
same = same.dropna()
fig, ax = plt.subplots()
ax.plot(same.index, same[0], marker="o", color=C[0], label="arrived by the promised date")
ax.plot(same.index, same[1], marker="o", color=C[7], label="arrived after the promised date")
ax.set_xlabel("actual delivery time (days)")
ax.set_ylabel("average review score")
ax.set_ylim(1, 5)
ax.set_title("Same delivery time, very different reviews: the promise sets the expectation")
ax.legend()
plt.show()
print(f"Average gap at equal delivery time: {(same[0] - same[1]).mean():.2f} stars")

# %% [markdown]
# ## 4. What a day is worth
#
# The slope on each side of the promise (stars per day), from the regression above without controls:

# %%
def slopes(df, h=10):
    w = df[df["margin"].between(-h, h)]
    early = LinearRegression().fit(w.loc[w["margin"] >= 0, ["margin"]], w.loc[w["margin"] >= 0, "review_score"]).coef_[0]
    late = LinearRegression().fit(w.loc[w["margin"] < 0, ["margin"]], w.loc[w["margin"] < 0, "review_score"]).coef_[0]
    return early, late


early_slope, late_slope = slopes(o)
print(f"Each extra day early:  {early_slope:+.3f} stars")
print(f"Each extra day late:   {-late_slope:+.3f} stars")
first = o[o["margin"].isin([0, -1])].groupby("margin")["review_score"].agg(["mean", lambda s: (s == 1).mean()])
print(f"First day late vs on the day: {first.loc[-1, 'mean']:.2f} vs {first.loc[0, 'mean']:.2f} stars; 1-star share "
      f"{first.iloc[0, 1]:.0%} vs {first.iloc[1, 1]:.0%}")
print(f"A day late costs about {abs(late_slope / early_slope):.0f}x what a day early earns.")

# %% [markdown]
# ## 5. Setting a better promise
#
# Olist's promises are long and safe: 23 days on average for 12-day deliveries. A shorter promise
# probably sells more (customers compare delivery dates at checkout), but every late order costs
# reviews. We model the **distribution** of delivery time from what is known at checkout and set the
# promise at a chosen quantile: a higher quantile means longer, safer promises.
#
# Inputs: distance between seller and customer, their states, category, weight, volume, price,
# freight, number of items and sellers, purchase weekday and month, and the seller's own recent
# delivery times (computed only from that seller's *earlier* orders, to avoid leakage).

# %%
o = o.sort_values("order_purchase_timestamp").reset_index(drop=True)
# Seller's median delivery time over their previous 20 delivered orders (known at checkout).
o["seller_hist_days"] = (o.groupby("seller_id")["actual_days"]
                          .transform(lambda s: s.shift(1).rolling(20, min_periods=3).median()))
o["seller_hist_orders"] = o.groupby("seller_id").cumcount()
for col in ["customer_state", "seller_state", "category"]:
    o[col + "_c"] = o[col].astype("category")
features = ["distance_km", "customer_state_c", "seller_state_c", "category_c", "product_weight_g", "volume_cm3",
            "price", "freight", "n_items", "n_sellers", "seller_hist_days", "seller_hist_orders"]
o["weekday"] = o["order_purchase_timestamp"].dt.weekday
o["month"] = o["order_purchase_timestamp"].dt.month
features += ["weekday", "month"]

# Orders purchased late in the data period have not all been delivered yet; stop at the end of July 2018.
data = o[o["order_purchase_timestamp"] < "2018-08-01"]
cut = data["order_purchase_timestamp"].quantile(0.8)
train, test = data[data["order_purchase_timestamp"] < cut], data[data["order_purchase_timestamp"] >= cut]
print(f"train: {len(train):,} orders to {cut:%d %b %Y}; test: {len(test):,} orders after")

quantiles = [0.5, 0.7, 0.8, 0.85, 0.9, 0.93, 0.95, 0.97]
promise = {}
for q in quantiles:
    m = HistGradientBoostingRegressor(loss="quantile", quantile=q, max_iter=300, learning_rate=0.05,
                                      categorical_features="from_dtype", random_state=0)
    m.fit(train[features], train["actual_days"])
    promise[q] = np.ceil(m.predict(test[features]))
# Baseline: the same quantile per customer state x seller state route, from the training orders.
route_q = {q: train.groupby(["customer_state", "seller_state"])["actual_days"].quantile(q) for q in quantiles}

# %% [markdown]
# Each policy is scored on the test orders by: average promise length, share of late orders, and
# the **expected review score**, predicted from how early or late each order would have arrived
# under that promise, using the review curve from the training period.

# %%
score_curve = train.groupby(train["margin"].clip(-15, 20))["review_score"].mean()


def expected_score(margin):
    return pd.Series(np.clip(margin, -15, 20)).map(score_curve).fillna(score_curve.mean()).mean()


actual_days_test = np.ceil(test["actual_days"].to_numpy())
results = [{"policy": "Olist's actual promise", "avg promise (days)": test["promise_days"].mean(),
            "late %": 100 * test["late"].mean(), "expected review": expected_score(test["margin"].to_numpy())}]
for q in quantiles:
    p = np.maximum(promise[q], 1)
    margin = p - actual_days_test
    results.append({"policy": f"model, quantile {q:.2f}", "avg promise (days)": p.mean(),
                    "late %": 100 * (margin < 0).mean(), "expected review": expected_score(margin)})
    rp = test.set_index(["customer_state", "seller_state"]).index.map(route_q[q]).to_numpy(dtype=float)
    rp = np.ceil(np.where(np.isnan(rp), np.nanmedian(rp), rp))
    margin_r = rp - actual_days_test
    results.append({"policy": f"route rule, quantile {q:.2f}", "avg promise (days)": rp.mean(),
                    "late %": 100 * (margin_r < 0).mean(), "expected review": expected_score(margin_r)})
res = pd.DataFrame(results).round(2)

fig, ax = plt.subplots(figsize=(10, 5))
for kind, color in (("model", C[0]), ("route rule", C[3])):
    r = res[res["policy"].str.startswith(kind)]
    ax.plot(r["avg promise (days)"], r["late %"], marker="o", color=color, label=f"{kind} (quantile 0.50 to 0.97)")
olist = res.iloc[0]
ax.scatter(olist["avg promise (days)"], olist["late %"], s=120, color=C[7], zorder=3, label="Olist's actual promise")
ax.set_xlabel("average promised delivery time (days)")
ax.set_ylabel("late orders (%)")
ax.set_title("The promise frontier on test orders: Olist sits close to it")
ax.legend()
plt.show()
res

# %%
def promise_at(kind, late):
    r = res[res["policy"].str.startswith(kind)].sort_values("late %")
    return np.interp(late, r["late %"], r["avg promise (days)"])


for kind in ("model", "route rule"):
    days = promise_at(kind, olist["late %"])
    print(f"{kind}: at Olist's lateness ({olist['late %']:.1f}%) it would promise {days:.1f} days on average, "
          f"vs Olist's {olist['avg promise (days)']:.1f} ({days - olist['avg promise (days)']:+.1f} days)")

# %% [markdown]
# Olist's promises turn out to be close to the frontier: at the same lateness, the best model saves only
# about two days. A 24-day promise for a 12-day delivery is not lazy padding. It is what the **tail** of
# delivery times demands.
#
# ## 6. Why promises must be long: the tail
#
# A promise that is rarely missed has to cover the slowest few percent of orders. How far is the tail
# from the typical order, and where does it come from?

# %%
q = data["actual_days"].quantile([0.5, 0.9, 0.95, 0.97])
print("Delivery time quantiles (days):", q.round(1).to_dict())
print(f"The 95th percentile is {q[0.95] / q[0.5]:.1f}x the median.")
d = data.dropna(subset=["seller_hist_days"]).copy()
d["seller_speed"] = pd.qcut(d["seller_hist_days"], 5, labels=["fastest 20%", "2nd", "3rd", "4th", "slowest 20%"])
d["distance"] = pd.qcut(d["distance_km"], 5, labels=["closest 20%", "2nd", "3rd", "4th", "farthest 20%"])
tail = d["actual_days"] > d["actual_days"].quantile(0.95)
pd.DataFrame({
    "quintile": ["1 (fastest / closest)", "2", "3", "4", "5 (slowest / farthest)"],
    "seller's recent speed: share in slowest 5%": tail.groupby(d["seller_speed"], observed=True).mean().round(3).to_numpy(),
    "distance: share in slowest 5%": tail.groupby(d["distance"], observed=True).mean().round(3).to_numpy(),
})

# %% [markdown]
# The slowest sellers and the longest routes produce most of the tail. That is where shorter promises
# would come from: reduce the slow tail (seller performance management, faster lanes to distant
# states) and the safe promise shrinks with it, while better prediction alone adds little.
#
# ## Takeaways for a marketplace
#
# - **Customers judge the promise, not the speed.** Arriving early earns almost nothing; arriving one
#   day late costs about half a star at once and more with every day. Orders with the same delivery
#   time get very different reviews depending on whether they beat the promise.
# - **The bend sits exactly at the promise**: the slope of reviews changes there sharply, with or without
#   controls for product, route, price and season, and not at placebo dates.
# - **Olist's long promises are not padding.** At the same lateness, a quantile model trained on
#   checkout-time information saves only about two days; a 24-day promise for a 12-day median delivery
#   is the price of a heavy tail.
# - **To promise faster, shrink the tail.** The slowest sellers and the longest routes make most of the
#   slowest 5% of orders. Improving them shortens the safe promise; better forecasting alone does not.
#
# Limitations: reviews are not randomly assigned, some customers review before delivery (Olist sends the
# survey around the promised date), and the expected-review calculation assumes the review curve stays
# the same when promises change.
#
# Data: Olist, Brazilian E-Commerce Public Dataset (CC BY-NC-SA 4.0).
