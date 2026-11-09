# %% [markdown]
# # Where discounts destroy profit: reverse-engineering the Superstore's costs
#
# Superstore notebooks usually show that "high discounts mean losses". This one goes further, because the
# data allows it: **every product's unit cost and list price can be recovered exactly** from Sales,
# Quantity, Discount and Profit. With them we can:
#
# 1. find the **break-even discount** of every product (its margin at list price);
# 2. measure how much profit is lost on sales discounted **below cost**, and where (states, sub-categories);
# 3. check whether deep discounts at least work as **loss leaders** that bring profitable baskets;
# 4. simulate simple **discount policies** and the volume increase each discount would need to pay off.

# %%
import glob
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

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


s = pd.read_csv(find("Sample - Superstore.csv"), encoding="latin-1")
print(f"{len(s):,} order lines, {s['Order ID'].nunique():,} orders, total sales {s['Sales'].sum():,.0f}, "
      f"profit {s['Profit'].sum():,.0f} ({s['Profit'].sum() / s['Sales'].sum():.1%} margin)")

# %% [markdown]
# ## 1. Recovering costs and list prices
#
# If profit is sales minus the cost of the goods, then for each line
# - unit cost = (Sales - Profit) / Quantity
# - list price = Sales / Quantity / (1 - Discount)
#
# If the data follows this logic, both numbers should be **identical on every line of the same product**,
# whatever the discount, quantity, region or date.

# %%
s["unit_cost"] = (s["Sales"] - s["Profit"]) / s["Quantity"]
s["list_price"] = s["Sales"] / s["Quantity"] / (1 - s["Discount"])
key = ["Product ID", "Product Name"]  # a few Product IDs are shared by two different products
spread = s.groupby(key).agg(cost_spread=("unit_cost", lambda x: x.max() / x.min() - 1 if x.min() > 0 else 0),
                            price_spread=("list_price", lambda x: x.max() / x.min() - 1), lines=("Sales", "size"))
multi = spread[spread["lines"] > 1]
print(f"{len(spread):,} products; of the {len(multi):,} sold more than once, unit cost is constant (within 0.1%) for "
      f"{(multi['cost_spread'] < 0.001).mean():.1%} and list price for {(multi['price_spread'] < 0.001).mean():.1%}")
s["list_margin"] = 1 - s["unit_cost"] / s["list_price"]
s.groupby("Category")["list_margin"].describe()[["mean", "min", "50%", "max"]].round(3)

# %% [markdown]
# Every product has one cost and one list price, and its **margin at list price** (between 0% and 50%)
# is the **break-even discount**: any discount above it sells the product below cost. (Such exact
# regularity also tells us the dataset is generated, as Tableau's sample data is; its logic is still a
# useful model of a retailer.)
#
# ## 2. How often does the Superstore sell below cost?

# %%
s["below_cost"] = s["Discount"] > s["list_margin"] + 1e-9
s["revenue_given_away"] = s["Quantity"] * s["list_price"] * s["Discount"]
lost = s.loc[s["below_cost"], "Profit"].sum()
print(f"Lines sold below cost: {s['below_cost'].mean():.1%} of lines, {s.loc[s['below_cost'], 'Sales'].sum() / s['Sales'].sum():.1%} "
      f"of sales; their profit is {lost:,.0f}, against {s.loc[~s['below_cost'], 'Profit'].sum():,.0f} on all other lines")
by_disc = s.groupby("Discount").agg(lines=("Sales", "size"), sales=("Sales", "sum"), profit=("Profit", "sum"),
                                    below_cost_share=("below_cost", "mean"))
fig, ax = plt.subplots()
ax.bar(by_disc.index.astype(str), by_disc["profit"] / 1e3, color=np.where(by_disc["profit"] < 0, C[7], C[0]))
ax.set_xlabel("discount")
ax.set_ylabel("total profit (thousands)")
ax.set_title("Profit by discount level: everything above 20% loses money in total")
plt.show()
by_disc.round(3)

# %% [markdown]
# Where do the below-cost sales happen?

# %%
fig, axes = plt.subplots(1, 2, figsize=(13, 5))
st = s.groupby("State").agg(profit=("Profit", "sum"), below=("below_cost", "mean"), sales=("Sales", "sum"))
st = st[st["sales"] > 20000].sort_values("profit")
axes[0].barh(st.index, st["profit"] / 1e3, color=np.where(st["profit"] < 0, C[7], C[0]))
axes[0].set_title("Profit by state (states with sales > 20k)")
axes[0].set_xlabel("profit (thousands)")
axes[0].grid(axis="y", visible=False)
sc = s.groupby("Sub-Category").agg(profit=("Profit", "sum"), lost=("Profit", lambda p: p[s.loc[p.index, "below_cost"]].sum()))
sc = sc.sort_values("lost")
axes[1].barh(sc.index, sc["lost"] / 1e3, color=C[7], label="profit on below-cost lines")
axes[1].barh(sc.index, sc["profit"] / 1e3, color=C[0], alpha=0.5, label="total profit")
axes[1].set_title("Sub-categories: losses on below-cost lines vs total profit")
axes[1].set_xlabel("thousands")
axes[1].legend(fontsize=8.5)
axes[1].grid(axis="y", visible=False)
plt.tight_layout()
plt.show()
worst = sc.sort_values("lost").head(4)
print("Largest losses on below-cost lines:", {k: f"{v:,.0f}" for k, v in worst["lost"].items()})
st.sort_values("below", ascending=False).head(8).round(3)

# %% [markdown]
# A handful of states (Texas, Illinois, Pennsylvania, Ohio, ...) give deep discounts on almost every
# order and lose money overall, while neighbouring states with list-price policies make a profit on the
# same products.
#
# ## 3. Are deep discounts loss leaders?
#
# A below-cost discount can still pay if it brings customers who buy other, profitable things. If so,
# the **rest of the basket** in orders with a below-cost line should be more profitable than in other
# orders.

# %%
orders = s.groupby("Order ID").agg(lines=("Sales", "size"), has_below=("below_cost", "any"))
rest = s[~s["below_cost"]].groupby("Order ID").agg(rest_profit=("Profit", "sum"), rest_sales=("Sales", "sum"),
                                                     rest_lines=("Sales", "size"))
orders = orders.join(rest, how="left").fillna({"rest_profit": 0, "rest_sales": 0, "rest_lines": 0})
multi_line = orders[orders["lines"] > 1]
comparison = multi_line.groupby("has_below").agg(orders=("lines", "size"), other_lines_per_order=("rest_lines", "mean"),
                                                 profit_of_other_lines=("rest_profit", "mean"),
                                                 sales_of_other_lines=("rest_sales", "mean"))
comparison.index = comparison.index.map({True: "order has a below-cost line", False: "no below-cost line"})
comparison["profit per other line"] = comparison["profit_of_other_lines"] / comparison["other_lines_per_order"]
comparison.round(2)

# %% [markdown]
# Orders with a below-cost line come with **smaller and less profitable** baskets: fewer other items, and
# less profit per other item. There is no sign of a loss-leader effect; deep discounts seem to go with
# deal-hunting orders, not with bigger baskets.
#
# ## 4. Discount policies
#
# What would profit have been under simpler rules, **if customers had bought the same quantities**? (This
# is the upper bound of the saving: some customers would buy less without the discount.)

# %%
def profit_under(discount):
    price = s["list_price"] * (1 - discount)
    return ((price - s["unit_cost"]) * s["Quantity"]).sum(), (price * s["Quantity"]).sum()


policies = {
    "actual discounts": s["Discount"],
    "cap every discount at 20%": s["Discount"].clip(upper=0.2),
    "never below cost (cap at the product's margin)": np.minimum(s["Discount"], s["list_margin"]),
    "never below a 10% margin": np.minimum(s["Discount"], (s["list_margin"] - 0.10).clip(lower=0)),
    "no discounts at all": s["Discount"] * 0,
}
rows = []
for name, d in policies.items():
    p, r = profit_under(d)
    rows.append({"policy": name, "sales": r, "profit": p, "margin %": 100 * p / r})
pol = pd.DataFrame(rows)
base = pol.iloc[0]
pol["profit vs actual"] = pol["profit"] - base["profit"]
pol["sales vs actual %"] = 100 * (pol["sales"] / base["sales"] - 1)
pol.round(1)

# %% [markdown]
# Higher prices raise revenue too at fixed quantities, so the real question is how many customers would
# walk away. For the "never below cost" rule the answer is simple: the lines it changes have **negative**
# profit, so it improves profit even if every one of those customers bought nothing at all.

# %%
affected = s["below_cost"]
print(f"Profit on the lines the 'never below cost' rule changes: {s.loc[affected, 'Profit'].sum():,.0f}. Dropping them "
      f"entirely would raise profit from {s['Profit'].sum():,.0f} to {s.loc[~affected, 'Profit'].sum():,.0f}.")

# %% [markdown]
# How much more volume would a discount need to beat selling at the capped price? For a product with list
# margin `m`, a discount `d` leaves a unit profit of `list x (m - d)`. Compared with a 20% discount, the
# volume needed is `(m - 0.2) / (m - d)` times larger, and **infinite when d > m**: no amount of extra
# volume makes a below-cost sale profitable.

# %%
need = s[(s["Discount"] > 0.2)].copy()
need["volume_multiple_needed"] = np.where(need["list_margin"] > need["Discount"],
                                          (need["list_margin"] - 0.2).clip(lower=0) / (need["list_margin"] - need["Discount"]),
                                          np.inf)
print(f"Lines discounted above 20%: {len(need):,}; of those, {np.isinf(need['volume_multiple_needed']).mean():.0%} are below "
      "cost, where no volume increase can pay.")

# %% [markdown]
# ## Takeaways
#
# - **The Superstore's profit follows a simple cost model**: one unit cost and one list price per product,
#   recovered exactly. Each product's margin at list price is its break-even discount (0-50%).
# - **About one line in five is sold below cost** (19% of lines, 20% of sales), losing 156k against 443k
#   earned on all other lines, concentrated in a few states with blanket deep-discount practices.
# - **No loss-leader effect**: orders with below-cost lines bring smaller, less profitable baskets.
# - **A "never below cost" rule** raises profit from 286k to at least 443k: the lines it changes lose money,
#   so it pays even if all those customers walked away. 97% of discounts above 20% are below cost, where no
#   volume increase could ever pay.
#
# Data: Superstore sample dataset (Tableau), as shared on Kaggle by vivek468.
