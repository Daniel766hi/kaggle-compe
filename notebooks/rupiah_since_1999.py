# %% [markdown]
# # Rupiah since 1999: crises, trends and how to use the data
#
# This notebook explores **[Rupiah (IDR) Daily Exchange Rates](https://www.kaggle.com/datasets/danielaijdkx/rupiah-idr-daily-exchange-rates)**,
# a dataset that is refreshed every day from the European Central Bank's reference rates.
#
# **What you will find here**
# 1. Today's rupiah rates and how they changed over 1 month and 1 year
# 2. The rupiah against the US dollar since 1999, and its sharpest monthly falls
# 3. Which currencies the rupiah lost the most (and least) against since 2010
# 4. How volatile the rupiah is, and when volatility spiked
# 5. A practical recipe: converting a column of IDR amounts to USD at the right date
#
# All numbers below are computed from the data when the notebook runs, so they stay current.

# %%
import glob
import os

import matplotlib.pyplot as plt
import matplotlib.transforms as mtransforms
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
    """Locate a dataset file on Kaggle (/kaggle/input) or locally (DATA_ROOT)."""
    for root in ("/kaggle/input", os.environ.get("DATA_ROOT", "../input")):
        hits = glob.glob(f"{root}/**/{name}", recursive=True)
        if hits:
            return hits[0]
    raise FileNotFoundError(name)


def label_ends(ax, items, x_pad_days=30):
    """Direct labels at line ends, nudged apart so they never overlap.
    items: list of (series, text, color)."""
    trans = mtransforms.offset_copy(ax.transData, fig=ax.figure, x=8, y=0, units="points")
    lo, hi = ax.get_ylim()
    gap, placed = (hi - lo) * 0.05, []
    ends = [(s.dropna().index[-1], s.dropna().iloc[-1], t, c) for s, t, c in items]
    for x, y, text, color in sorted(ends, key=lambda e: e[1]):
        y_text = max(y, placed[-1] + gap) if placed else y
        placed.append(y_text)
        ax.plot(x, y, "o", color=color, ms=5, zorder=3)
        ax.text(x, y_text, text, transform=trans, va="center", color=INK, fontsize=9.5)


def note(ax, x, y, text, dy=28, ha="center"):
    """An annotation with a background, so it stays readable over lines."""
    ax.annotate(text, (x, y), xytext=(0, dy), textcoords="offset points", ha=ha, fontsize=9, color=INK,
                bbox=dict(boxstyle="round,pad=0.25", fc=SURFACE, ec="none", alpha=0.9),
                arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))


# %%
rates = pd.read_csv(find("idr_exchange_rates.csv"), parse_dates=["date"]).set_index("date")
monthly = pd.read_csv(find("idr_monthly_average.csv"), parse_dates=["month"])
print(f"{len(rates):,} trading days, {rates.index.min():%Y-%m-%d} to {rates.index.max():%Y-%m-%d}")
rates.tail(3)[["idr_per_usd", "idr_per_eur", "idr_per_sgd", "idr_per_jpy", "idr_per_cny", "idr_per_myr"]].round(2)

# %% [markdown]
# Each row is one day; `idr_per_usd` is **how many rupiah one US dollar costs**. A higher number
# means a **weaker rupiah**. The ECB publishes rates on European working days only, so weekends
# and holidays have no row.
#
# ## 1. Today's rates and recent change

# %%
majors = ["usd", "eur", "sgd", "jpy", "cny", "myr", "aud", "gbp"]
latest = rates.iloc[-1]


def value_on_or_before(days_ago):
    return rates[rates.index <= rates.index[-1] - pd.Timedelta(days=days_ago)].iloc[-1]


summary = pd.DataFrame({
    "IDR per unit": latest[[f"idr_per_{c}" for c in majors]].values,
    "1-month change %": ((latest / value_on_or_before(30) - 1) * 100)[[f"idr_per_{c}" for c in majors]].values,
    "1-year change %": ((latest / value_on_or_before(365) - 1) * 100)[[f"idr_per_{c}" for c in majors]].values,
}, index=[c.upper() for c in majors]).round(2)
print(f"Rates on {rates.index[-1]:%d %B %Y}. Positive change = rupiah weakened against that currency.")
summary

# %% [markdown]
# ## 2. The rupiah against the US dollar since 1999

# %%
usd = rates["idr_per_usd"]
fig, ax = plt.subplots()
ax.plot(usd.index, usd, color=C[0], lw=1.6)
ax.set_title("Rupiah per US dollar, daily since 1999 (higher = weaker rupiah)")
ax.set_ylabel("IDR per USD")
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))

# Mark the three sharpest monthly moves, found from the data.
month_end = usd.resample("ME").last()
moves = (month_end.pct_change() * 100).nlargest(3)
for when, pct in moves.items():
    note(ax, when, usd.loc[:when].iloc[-1], f"{when:%b %Y}\n+{pct:.1f}% in a month", dy=32)
plt.tight_layout()
plt.show()

print("Sharpest monthly depreciations of the rupiah against the USD:")
(month_end.pct_change() * 100).nlargest(6).round(1).rename("USD/IDR change in the month, %").to_frame()

# %% [markdown]
# The biggest monthly falls line up with well-known shocks:
# - **October-November 2008**: the global financial crisis.
# - **March 2020**: the start of the COVID-19 pandemic.
# - **1999 and 2001**: the turbulent years after the 1997-98 Asian financial crisis.
# - **August 2013**: the "taper tantrum", when markets feared the US Federal Reserve would stop
#   its bond buying.
#
# In the global shocks, investors pulled money out of emerging markets all at once.
#
# ## 3. Against which currencies did the rupiah lose most?
#
# Comparing raw rates is meaningless (1 JPY and 1 EUR are very different amounts), so each
# series is **indexed to its 2010 average = 100**. A value of 200 means that currency now costs
# twice as many rupiah as in 2010. Indexing keeps everything on one axis, without a misleading
# second y-axis.

# %%
compare = {"usd": "USD", "sgd": "SGD", "cny": "CNY", "eur": "EUR", "jpy": "JPY"}
base = rates.loc["2010", [f"idr_per_{c}" for c in compare]].mean()
indexed = rates[[f"idr_per_{c}" for c in compare]].loc["2010":] / base * 100
indexed = indexed.rolling(20, min_periods=1).mean()  # smooth daily noise

fig, ax = plt.subplots()
for i, (col, name) in enumerate(compare.items()):
    ax.plot(indexed.index, indexed[f"idr_per_{col}"], color=C[i], lw=1.8, label=name)
ax.axhline(100, color=INK2, lw=0.8, ls="--")
label_ends(ax, [(indexed[f"idr_per_{col}"], f"{name} {indexed[f'idr_per_{col}'].dropna().iloc[-1]:.0f}", C[i])
                for i, (col, name) in enumerate(compare.items())])
ax.set_title("Price of foreign currencies in rupiah, indexed (2010 average = 100)")
ax.set_ylabel("Index, 2010 = 100")
ax.legend(loc="upper left", ncols=5)
ax.set_xlim(indexed.index.min(), indexed.index.max() + pd.Timedelta(days=550))
plt.tight_layout()
plt.show()

# %% [markdown]
# Two things stand out:
# - The rupiah **lost the most against the Singapore dollar, the US dollar and the Chinese yuan**,
#   Indonesia's key trading and financing currencies.
# - Against the **Japanese yen** the rupiah was much more stable, because the yen itself
#   weakened a lot over the same period.
#
# ## 4. Volatility: how much does the rupiah move?
#
# Volatility here is the standard deviation of daily log changes over the past 21 trading days
# (about one month), annualised. It is a standard way to measure currency risk.

# %%
returns = np.log(usd).diff()
vol = returns.rolling(21).std() * np.sqrt(252) * 100

fig, ax = plt.subplots()
ax.plot(vol.index, vol, color=C[0], lw=1.2)
ax.set_title("USD/IDR volatility: annualised, rolling 21 trading days")
ax.set_ylabel("Volatility, % per year")
calm = vol.loc["2021":].median()
ax.axhline(calm, color=INK2, lw=0.8, ls="--")
ax.text(0.99, 0.92, f"dashed line: median since 2021 = {calm:.1f}%", transform=ax.transAxes,
        ha="right", fontsize=9, color=INK2)
plt.tight_layout()
plt.show()

period = ((vol.index.year - 1999) // 5) * 5 + 1999
labels = pd.Series(period, index=vol.index).map(lambda y: f"{y}-{min(y + 4, vol.index.year.max())}")
print("Highest volatility reading per period:")
vol.groupby(labels.values).max().round(1).rename_axis("period").rename("peak volatility, %").to_frame()

# %% [markdown]
# Volatility was extreme right after the 1997-98 Asian financial crisis, spiked again in 2008,
# 2013 and 2020, and has been **noticeably calmer in recent years**.
#
# ## 5. Recipe: convert IDR amounts to USD at the right date
#
# A common task: you have transactions in rupiah (sales, prices, financial statements) and need
# them in USD using the rate *valid on that date*. Because there is no rate on weekends and
# holidays, use `pd.merge_asof` to take the **most recent published rate**.

# %%
transactions = pd.DataFrame({
    "date": pd.to_datetime(["2008-10-27", "2020-03-23", "2024-12-25"]),  # the last one is a holiday
    "amount_idr": [1_000_000_000, 1_000_000_000, 1_000_000_000],
})
converted = pd.merge_asof(
    transactions.sort_values("date"),
    rates[["idr_per_usd"]].reset_index().rename(columns={"date": "rate_date"}),
    left_on="date", right_on="rate_date", direction="backward",
)
converted["amount_usd"] = (converted["amount_idr"] / converted["idr_per_usd"]).round(0)
converted

# %% [markdown]
# The same one billion rupiah was worth very different amounts of dollars in each year.
#
# ## Monthly averages for reporting
#
# `idr_monthly_average.csv` already contains the monthly mean, low and high for 12 currencies,
# which is handy for budgets and monthly reports:

# %%
monthly[monthly["currency"] == "USD"].tail(6).set_index(["month", "currency"]).round(0)

# %% [markdown]
# ## Notes and ideas
#
# - These are **ECB reference rates** (around 14:15 CET), not Bank Indonesia's JISDOR rate or
#   bank buy/sell rates, so they can differ slightly from local quotes.
# - Ideas to extend this notebook: forecast USD/IDR with a time-series model, relate the rupiah
#   to commodity prices (coal, palm oil), or measure the cost of imports from different countries.
#
# *If you found this useful, an upvote on the notebook and the dataset helps others find them.*
