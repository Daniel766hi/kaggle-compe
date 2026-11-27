# %% [markdown]
# # Who follows the Fed? Seventy years of central bank policy rates
#
# This notebook explores **[Central Bank Policy Rates: 40+ Banks, Daily](https://www.kaggle.com/datasets/danielaijdkx/central-bank-policy-rates-daily-bis)**,
# the BIS collection of central bank policy rates. Statistical data for analysis, not investment advice.
#
# **Questions answered**
# 1. How did the 2022-23 tightening compare across central banks, and how much has been unwound?
# 2. How often do central banks move, and by how much?
# 3. Does Bank Indonesia move in step with the Fed?
# 4. Which moves are really changes of instrument, not policy?
#
# The numbers in the text are computed from the data each time the notebook runs.

# %%
import glob
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

INK2, GRID, SURFACE = "#52514e", "#e6e5e0", "#fcfcfb"
plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE, "axes.edgecolor": GRID,
    "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "axes.grid": True, "grid.color": GRID,
    "axes.axisbelow": True, "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
    "axes.titlesize": 13, "axes.titleweight": "bold", "axes.titlelocation": "left", "font.size": 10.5,
    "figure.figsize": (11, 4.6), "figure.dpi": 110, "legend.frameon": False,
})


def find(name):
    for root in ("/kaggle/input", os.environ.get("DATA_ROOT", "../input")):
        hits = glob.glob(f"{root}/**/{name}", recursive=True)
        if hits:
            return hits[0]
    raise FileNotFoundError(name)


daily = pd.read_parquet(find("policy_rates_daily.parquet"))
monthly = pd.read_csv(find("policy_rates_monthly.csv"), parse_dates=["month"])
moves = pd.read_csv(find("rate_changes.csv"), parse_dates=["date"])
latest = pd.read_csv(find("latest.csv"), parse_dates=["date", "last_move_date"])
current = latest[latest["date"] >= latest["date"].max() - pd.Timedelta(days=60)]  # banks still publishing
print(f"{daily['country_code'].nunique()} central banks, {daily['date'].min():%Y}-{daily['date'].max():%Y}; "
      f"{len(moves):,} rate moves; {len(current)} banks with current data")

# %% [markdown]
# ## 1. The 2022-23 tightening and its unwinding
#
# For each bank still publishing: the rate at the start of 2022, the peak since then, and today. Banks with rates
# above 30% at the peak are left out of the chart to keep the scale readable.

# %%
start = daily[daily["date"] <= "2022-01-01"].sort_values("date").groupby("country_code").tail(1).set_index("country_code")["rate_pct"]
c = current.set_index("country_code").assign(start=start).dropna(subset=["start", "peak_since_2022_pct"])
c["hiked_bp"] = (c["peak_since_2022_pct"] - c["start"]) * 100
c = c[c["peak_since_2022_pct"] <= 30].sort_values("hiked_bp")
fig, ax = plt.subplots(figsize=(11, 9))
y = np.arange(len(c))
ax.hlines(y, c["start"], c["peak_since_2022_pct"], color=GRID, lw=6)
ax.scatter(c["start"], y, color=INK2, s=25, label="Start of 2022", zorder=3)
ax.scatter(c["peak_since_2022_pct"], y, color="#e34948", s=30, label="Peak since", zorder=3)
ax.scatter(c["rate_pct"], y, color="#2a78d6", s=30, label="Now", zorder=4)
ax.set_yticks(y, c["country"]); ax.set_xlabel("Policy rate (%)"); ax.grid(axis="y", visible=False)
ax.set_title("From 2022 to the peak to now"); ax.legend(loc="lower right")
plt.show()
unwound = (c["peak_since_2022_pct"] - c["rate_pct"]) / (c["peak_since_2022_pct"] - c["start"]).replace(0, np.nan)
print(f"Median hike from start-2022 to peak: {c['hiked_bp'].median():.0f} bp. Median share of that hike since unwound: "
      f"{unwound.median():.0%}.")

# %% [markdown]
# ## 2. How central banks move
#
# Moves since 2000 (excluding those on documented break dates): size and frequency.

# %%
m = moves[(moves["date"] >= "2000-01-01") & ~moves["possible_break"]]
size = m["change_bp"].abs().round(0).value_counts().sort_index()
common = size[size.index.isin([10, 15, 20, 25, 50, 75, 100])]
print("Most common move sizes since 2000 (bp):", ", ".join(f"{int(k)}: {v:,}" for k, v in size.sort_values(ascending=False).head(6).items()))
per_year = m.assign(year=m["date"].dt.year).groupby(["country", "year"]).size().groupby("country").mean().sort_values()
fig, ax = plt.subplots(figsize=(11, 8))
show = per_year[per_year.index.isin(current["country"])]
ax.barh(show.index, show.values, color="#6250d6"); ax.grid(axis="y", visible=False)
ax.set_xlabel("Average rate moves per year with any move, since 2000"); ax.set_title("How active each central bank is")
plt.show()

# %% [markdown]
# ## 3. Does Bank Indonesia move with the Fed?
#
# Month-end policy rates since 2005, and the correlation of 12-month changes.

# %%
w = monthly.pivot(index="month", columns="country_code", values="rate_pct")
w = w[w.index >= "2005-07-01"]
fig, ax = plt.subplots()
for code, color, label in (("ID", "#eb6834", "Bank Indonesia"), ("US", "#2a78d6", "US Federal Reserve"),
                           ("MY", "#1baf7a", "Bank Negara Malaysia"), ("PH", "#e87ba4", "Bangko Sentral ng Pilipinas")):
    if code in w:
        ax.plot(w.index, w[code], color=color, label=label, lw=1.8)
ax.axvline(pd.Timestamp("2016-08-19"), color=INK2, lw=1, ls=":")
ax.text(pd.Timestamp("2016-09-01"), ax.get_ylim()[1] * 0.92, "BI changes instrument\n(not a cut)", fontsize=8.5, color=INK2)
ax.set_ylabel("Policy rate (%)"); ax.set_title("Policy rates since 2005"); ax.legend(ncol=2)
plt.show()
ch = w.diff(12)
for code in ("ID", "MY", "PH", "TH", "KR", "IN"):
    if code in ch and "US" in ch:
        pair = ch[["US", code]].dropna()
        print(f"Correlation of 12-month changes with the Fed, {code}: {pair.corr().iloc[0, 1]:.2f} ({len(pair)} months)")

# %% [markdown]
# ## 4. Breaks: changes of instrument that look like moves
#
# Moves that fall on a day or month the BIS break notes mention. Read the note before treating one as policy.

# %%
br = moves[moves["possible_break"]].sort_values("date")
print(br[["date", "country", "old_rate_pct", "new_rate_pct", "change_bp"]].to_string(index=False))

# %% [markdown]
# ## Takeaways
#
# - Section 1 shows how far each bank tightened after 2022 and how much it has since cut.
# - 25 bp is the standard step; section 2 prints the most common sizes and how active each bank is.
# - Bank Indonesia's moves are correlated with the Fed's to the degree printed in section 3, together with its
#   neighbours.
# - Always check the break notes: Bank Indonesia's August 2016 "cut" was a change of instrument.
#
# **Limits**: policy rates are set differently across countries (target ranges are recorded at the midpoint for
# some); this is descriptive data, not a forecast or investment advice.
