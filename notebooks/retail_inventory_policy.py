# %% [markdown]
# # From transactions to stock levels: an inventory policy for Online Retail II
#
# This dataset is usually used for RFM segmentation and market baskets. But it is the order book of a
# **wholesaler**: a UK company selling gift items, mostly to shops. The question its operations team
# faces every week is different: **how much of each item to keep in stock**.
#
# This notebook turns two years of invoices into an inventory policy and tests it on the last 26 weeks:
# 1. **ABC analysis**: which items carry the revenue.
# 2. **Demand classification** (Syntetos-Boylan): smooth, erratic, intermittent or lumpy.
# 3. **Why demand is erratic**: a few very large orders.
# 4. **Forecast backtest**: naive, moving average, exponential smoothing, Croston/SBA, seasonal naive.
# 5. **Inventory simulation**: a weekly order-up-to policy with a 2-week lead time, tracing fill rate
#    against stock value, with and without **handling large orders separately**.

# %%
import glob
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

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


raw = pd.read_csv(find("online_retail_II.csv"), dtype={"StockCode": str, "Invoice": str})
raw["InvoiceDate"] = pd.to_datetime(raw["InvoiceDate"])
# Sales lines only: no cancellations (invoice "C..."), returns, free items or non-product codes (postage, fees).
s = raw[~raw["Invoice"].str.startswith("C") & (raw["Quantity"] > 0) & (raw["Price"] > 0)].copy()
s = s[s["StockCode"].str.match(r"^\d{5}[A-Za-z]?$", na=False)]
s["revenue"] = s["Quantity"] * s["Price"]
s["week"] = s["InvoiceDate"].dt.to_period("W-SUN").dt.start_time
s = s[s["week"] < s["week"].max()]  # the last week is incomplete
print(f"{len(s):,} sales lines, {s['StockCode'].nunique():,} items, {s['week'].min():%d %b %Y} to {s['week'].max():%d %b %Y}")

# %% [markdown]
# ## 1. ABC: which items matter

# %%
rev = s.groupby("StockCode")["revenue"].sum().sort_values(ascending=False)
share = rev.cumsum() / rev.sum()
abc = pd.Series(np.where(share <= 0.8, "A", np.where(share <= 0.95, "B", "C")), index=rev.index)
fig, ax = plt.subplots()
ax.plot(np.arange(1, len(share) + 1) / len(share) * 100, share * 100, color=C[0])
for cls, pct in (("A", 80), ("B", 95)):
    n = (share <= pct / 100).sum()
    ax.annotate(f"{cls}: {n:,} items ({n / len(share):.0%}) give {pct}% of revenue", (n / len(share) * 100, pct),
                xytext=(20, -25), textcoords="offset points", fontsize=9.5, arrowprops=dict(arrowstyle="-", color=INK2))
ax.set_xlabel("% of items (by revenue, largest first)")
ax.set_ylabel("% of revenue")
ax.set_title("A fifth of the items bring 80% of the revenue")
plt.show()

# %% [markdown]
# ## 2. What kind of demand? The Syntetos-Boylan classes
#
# Two numbers per item, on weekly demand: **ADI**, the average interval between weeks with demand, and
# **CV²**, the squared coefficient of variation of the non-zero weekly quantities. The cut-offs (1.32 and
# 0.49) are the classic ones for choosing a forecasting method.

# %%
weekly = s.groupby(["StockCode", "week"])["Quantity"].sum().unstack(fill_value=0)
weekly = weekly.reindex(columns=pd.date_range(weekly.columns.min(), weekly.columns.max(), freq="7D"), fill_value=0)
items = rev.index[:500]  # the 500 best-selling items: all A items and the top of B
W = weekly.loc[items]


def classify(row):
    nz = row[row > 0]
    adi = len(row) / max(len(nz), 1)
    cv2 = (nz.std() / nz.mean()) ** 2 if len(nz) > 1 else np.nan
    kind = ("smooth" if cv2 < 0.49 else "erratic") if adi < 1.32 else ("intermittent" if cv2 < 0.49 else "lumpy")
    return pd.Series({"ADI": adi, "CV2": cv2, "class": kind})


cls = W.apply(classify, axis=1)
fig, ax = plt.subplots(figsize=(8, 5.5))
for kind, color in zip(["smooth", "erratic", "intermittent", "lumpy"], [C[2], C[1], C[0], C[7]]):
    g = cls[cls["class"] == kind]
    ax.scatter(g["ADI"], g["CV2"], s=14, color=color, alpha=0.7, label=f"{kind} ({len(g)})")
ax.axvline(1.32, color=INK2, lw=0.8, ls="--")
ax.axhline(0.49, color=INK2, lw=0.8, ls="--")
ax.set_xscale("log")
ax.set_yscale("log")
ax.set_xlabel("ADI: average weeks between demands")
ax.set_ylabel("CV²: variability of order sizes")
ax.set_title("The 500 best sellers: most demand is erratic")
ax.legend()
plt.show()

# %% [markdown]
# ## 3. Why so erratic? Large orders
#
# A wholesaler sells to shops that order a few dozen, and occasionally to customers who order thousands.

# %%
lines = s[s["StockCode"].isin(items)].copy()
first_year = lines["week"] < lines["week"].min() + pd.Timedelta(weeks=52)
# "Large" order line: above the 95th percentile of that item's order-line sizes in the first year.
p95 = lines[first_year].groupby("StockCode")["Quantity"].quantile(0.95)
lines["large"] = lines["Quantity"] > lines["StockCode"].map(p95)
big_share = lines.groupby("large")["Quantity"].sum() / lines["Quantity"].sum()
print(f"Large order lines: {lines['large'].mean():.1%} of lines, {big_share[True]:.0%} of units sold")
cv_all = W.apply(lambda r: r.std() / r.mean(), axis=1)
base_weekly = lines[~lines["large"]].groupby(["StockCode", "week"])["Quantity"].sum().unstack(fill_value=0)
base_weekly = base_weekly.reindex(index=items, columns=W.columns, fill_value=0)
cv_base = base_weekly.apply(lambda r: r.std() / r.mean() if r.mean() > 0 else np.nan, axis=1)
print(f"Median weekly coefficient of variation: {cv_all.median():.2f} with all orders, {cv_base.median():.2f} "
      "without large order lines")

# %% [markdown]
# About one order line in twenty carries a large share of the volume, and without those lines weekly
# demand is far steadier. That suggests a common practice we will test: **stock for the regular demand,
# and serve large orders separately** (made to order, or quoted a longer delivery time).
#
# ## 4. Forecast backtest
#
# Last 26 weeks held out. Each method forecasts next week's demand from the weeks before it (rolling
# origin). Error is measured as MAE scaled by the item's mean demand, so items of all sizes count alike.

# %%
H = 26
weeks = W.columns
test_weeks = weeks[-H:]


def ses(x, alpha=0.2):
    level = x[: min(8, len(x))].mean()
    for v in x:
        level = alpha * v + (1 - alpha) * level
    return level


def croston(x, alpha=0.1, sba=True):
    nz = np.flatnonzero(x)
    if len(nz) == 0:
        return 0.0
    z, p, last = x[nz[0]], 1.0, nz[0]
    for t in nz[1:]:
        z = alpha * x[t] + (1 - alpha) * z
        p = alpha * (t - last) + (1 - alpha) * p
        last = t
    f = z / p
    return f * (1 - alpha / 2) if sba else f


METHODS = {
    "naive (last week)": lambda x: x[-1],
    "moving average 8w": lambda x: x[-8:].mean(),
    "exp. smoothing": ses,
    "Croston (SBA)": croston,
    "seasonal naive (52w ago)": lambda x: x[-52] if len(x) >= 52 else x[-8:].mean(),
}


def backtest(matrix):
    out = {}
    for name, f in METHODS.items():
        errs = []
        for item in matrix.index:
            x = matrix.loc[item].to_numpy(float)
            preds = np.array([f(x[: len(x) - H + h]) for h in range(H)])
            errs.append(np.abs(preds - x[-H:]).mean() / max(x[:-H].mean(), 1e-9))
        out[name] = pd.Series(errs, index=matrix.index)
    return pd.DataFrame(out)


bt = backtest(W)
summary = bt.groupby(cls["class"]).median().round(3)
summary.loc["all 500 items"] = bt.median().round(3)
summary

# %% [markdown]
# Exponential smoothing and the 8-week moving average are best overall; Croston (SBA) is close on smooth
# and erratic items but did not win on the intermittent or lumpy ones here, and last year's same week is
# the worst guide. (Intermittent items have huge scaled errors because their mean demand is small.) We
# use **exponential smoothing** for the inventory policy below.
#
# ## 5. Inventory simulation
#
# **Policy**: every week, order up to `S = forecast x (L + R) + z x sigma x sqrt(L + R)`, with review
# period R = 1 week and lead time L = 2 weeks. `sigma` is the standard deviation of the item's one-week
# forecast errors over the 26 weeks before the test period. Demand that cannot be served from stock is lost.
# For each safety factor `z` we record the **fill rate** (share of units served from stock) and the
# **average stock value** (units in stock x unit price).

# %%
L, R = 2, 1
price = s.groupby("StockCode")["Price"].median()


def sigma_of_errors(x, f=ses, n=26):
    end = len(x) - H
    errs = [x[t] - f(x[:t]) for t in range(end - n, end)]
    return np.std(errs)


def simulate(matrix, z, served_matrix=None):
    """Weekly order-up-to policy on the last H weeks. served_matrix: the demand the stock must serve
    (defaults to all demand)."""
    served_matrix = matrix if served_matrix is None else served_matrix
    filled = demanded = stock_value = 0.0
    for item in matrix.index:
        x = served_matrix.loc[item].to_numpy(float)
        sig = sigma_of_errors(x)
        start = len(x) - H
        on_hand = ses(x[:start]) * (L + R)
        pipeline = [0.0] * L
        for t in range(start, len(x)):
            on_hand += pipeline.pop(0)
            sold = min(on_hand, x[t])
            filled += sold
            demanded += x[t]
            on_hand -= sold
            stock_value += on_hand * price[item]
            target = ses(x[: t + 1]) * (L + R) + z * sig * np.sqrt(L + R)
            pipeline.append(max(0.0, target - on_hand - sum(pipeline)))
    return filled / demanded, stock_value / H


zs = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
all_demand = [simulate(W, z) for z in zs]
base_demand = [simulate(W, z, served_matrix=base_weekly) for z in zs]
frontier = pd.DataFrame({"z": zs,
                         "fill rate, all demand": [f for f, _ in all_demand],
                         "stock value, all demand": [v for _, v in all_demand],
                         "fill rate, regular demand": [f for f, _ in base_demand],
                         "stock value, regular demand": [v for _, v in base_demand]})
fig, ax = plt.subplots()
ax.plot(frontier["stock value, all demand"] / 1e3, 100 * frontier["fill rate, all demand"], marker="o", color=C[7],
        label="stock for all demand")
ax.plot(frontier["stock value, regular demand"] / 1e3, 100 * frontier["fill rate, regular demand"], marker="o",
        color=C[0], label="stock for regular demand; large orders served separately")
for _, r in frontier.iterrows():
    ax.annotate(f"z={r['z']:g}", (r["stock value, all demand"] / 1e3, 100 * r["fill rate, all demand"]),
                xytext=(5, -10), textcoords="offset points", fontsize=8, color=C[7])
ax.set_xlabel("average stock value (thousand GBP), 500 items")
ax.set_ylabel("fill rate (% of units served from stock)")
ax.set_title("Service vs stock: separating large orders shifts the frontier")
ax.legend(loc="lower right")
plt.show()
frontier.round(3)

# %%
def stock_for(target, fill, value):
    order = np.argsort(fill)
    return np.interp(target, np.asarray(fill)[order], np.asarray(value)[order])


for target in (0.90, 0.95):
    a = stock_for(target, frontier["fill rate, all demand"], frontier["stock value, all demand"])
    b = stock_for(target, frontier["fill rate, regular demand"], frontier["stock value, regular demand"])
    print(f"Fill rate {target:.0%}: stock value {a:,.0f} GBP for all demand vs {b:,.0f} GBP for regular demand "
          f"({1 - b / a:.0%} less)")

# %% [markdown]
# Note what the second curve measures: the fill rate on **regular** demand only. The large order lines
# (about a third of units) are not served from this stock; they are produced or bought to order, with a
# longer quoted lead time. The saving is in stock held, not in total supply.
#
# ## Takeaways for the operations team
#
# - **Focus**: a fifth of the items bring 80% of revenue; the policy above covers the 500 best sellers.
# - **Demand is mostly erratic**, and the reason is visible in the order book: a small share of very large
#   order lines carries a big part of the volume.
# - **Forecasting method matters less than the policy.** Smoothing methods beat naive ones, but the big
#   lever is what the stock is asked to cover.
# - **Serving large orders separately** (made to order, or a longer quoted lead time for quantities above
#   the usual) lets the same safety-stock rule reach a given fill rate on regular demand with about 70%
#   less stock value. Whether that is acceptable depends on how large customers react to a longer lead time, which the
#   data cannot show.
#
# Assumptions: weekly review, a fixed 2-week lead time for all items, lost sales, stock valued at the
# median selling price (cost prices are not in the data), and no capacity or budget limits.
#
# Data: Chen, D. (2019), Online Retail II, UCI Machine Learning Repository (CC BY 4.0).
