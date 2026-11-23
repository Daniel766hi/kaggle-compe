# %% [markdown]
# # ASEAN at a glance: growth, credit depth and logistics
#
# This notebook explores **[ASEAN & G20 Economies: 30 World Bank Indicators](https://www.kaggle.com/datasets/danielaijdkx/asean-g20-macro-indicators-world-bank)**.
#
# **Questions answered**
# 1. How fast have ASEAN economies grown, and how steady is that growth?
# 2. Where is inflation under control?
# 3. How deep is bank credit relative to income, and who is "under-banked"?
# 4. How do ASEAN members score on logistics and on manufacturing?
#
# The numbers in the text are computed from the data each time the notebook runs.

# %%
import glob
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

INK2, GRID, SURFACE = "#52514e", "#e6e5e0", "#fcfcfb"
C = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948", "#52514e", "#9ad0c2", "#b8860b"]
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


values = pd.read_csv(find("indicator_values.csv"))
countries = pd.read_csv(find("countries.csv"))
latest = pd.read_csv(find("latest.csv"))
asean = countries.loc[countries["asean"], "iso3"].tolist()
name = countries.set_index("iso3")["country"]
wide = lambda code: values[values["indicator"] == code].pivot(index="year", columns="iso3", values="value")
print(f"{values['iso3'].nunique()} countries/aggregates, {values['indicator'].nunique()} indicators, {values['year'].min()}-{values['year'].max()}")

# %% [markdown]
# ## 1. Growth: fast and steady?
#
# Average real GDP growth since 2010 against its volatility (standard deviation), ASEAN and the G20.

# %%
g = wide("NY.GDP.MKTP.KD.ZG")
g = g[g.index >= 2010]
stats = pd.DataFrame({"mean": g.mean(), "sd": g.std(), "n": g.count()})
stats = stats[(stats["n"] >= 10) & stats.index.isin(countries.loc[~countries["is_aggregate"], "iso3"])]
fig, ax = plt.subplots(figsize=(11, 6))
for iso, r in stats.iterrows():
    is_asean = iso in asean
    ax.scatter(r["sd"], r["mean"], s=70 if is_asean else 35, color="#eb6834" if is_asean else "#2a78d6", alpha=0.85)
    ax.annotate(name.get(iso, iso), (r["sd"], r["mean"]), fontsize=8.5, xytext=(4, 3), textcoords="offset points")
ax.set_xlabel("Volatility of growth since 2010 (standard deviation, pp)"); ax.set_ylabel("Average GDP growth since 2010 (%)")
ax.set_title("Growth vs volatility, 2010 onward (orange: ASEAN)")
plt.show()
best = stats.loc[stats.index.isin(asean)].assign(ratio=lambda d: d["mean"] / d["sd"]).sort_values("ratio", ascending=False)
print("Steadiest ASEAN growers (growth per unit of volatility):",
      ", ".join(f"{name[i]} {r['mean']:.1f}% ± {r['sd']:.1f}" for i, r in best.head(4).iterrows()))

# %% [markdown]
# ## 2. Inflation since 2015

# %%
inf = wide("FP.CPI.TOTL.ZG")
inf = inf[inf.index >= 2015][[c for c in asean if c in inf]]
fig, ax = plt.subplots()
for i, iso in enumerate(inf.columns):
    ax.plot(inf.index, inf[iso], label=name[iso], color=C[i % len(C)], lw=1.6)
ax.axhline(0, color=INK2, lw=0.8); ax.set_ylim(-3, min(25, inf.max().max() + 2))
ax.set_ylabel("Consumer price inflation (%)"); ax.set_title("ASEAN inflation since 2015 (axis capped at 25%)")
ax.legend(ncol=4, fontsize=8.5)
plt.show()
lt = latest[latest["indicator"] == "FP.CPI.TOTL.ZG"].set_index("iso3")
print("Latest inflation:", ", ".join(f"{name[i]} {lt.loc[i, 'latest_value']:.1f}% ({int(lt.loc[i, 'latest_year'])})"
                                       for i in asean if i in lt.index))

# %% [markdown]
# ## 3. Credit depth vs income: who is under-banked?
#
# Domestic credit to the private sector (% of GDP) against GDP per capita (PPP), latest year for each. Countries
# below the fitted line have less bank credit than their income level would suggest.

# %%
lt = latest.pivot(index="iso3", columns="indicator", values="latest_value")
d = lt[["FS.AST.PRVT.GD.ZS", "NY.GDP.PCAP.PP.KD"]].dropna()
d = d[d.index.isin(countries.loc[~countries["is_aggregate"], "iso3"])]
x, y = np.log(d["NY.GDP.PCAP.PP.KD"]), d["FS.AST.PRVT.GD.ZS"]
slope, intercept = np.polyfit(x, y, 1)
d["gap"] = y - (intercept + slope * x)
fig, ax = plt.subplots(figsize=(11, 6))
ax.scatter(d["NY.GDP.PCAP.PP.KD"], y, color=["#eb6834" if i in asean else "#2a78d6" for i in d.index], s=50)
xs = np.linspace(x.min(), x.max(), 50)
ax.plot(np.exp(xs), intercept + slope * xs, color=INK2, lw=1, ls="--")
for iso in d.index:
    ax.annotate(name.get(iso, iso), (d.loc[iso, "NY.GDP.PCAP.PP.KD"], y[iso]), fontsize=8.5, xytext=(4, 3), textcoords="offset points")
ax.set_xscale("log"); ax.set_xlabel("GDP per capita, PPP (log scale)"); ax.set_ylabel("Private credit (% of GDP)")
ax.set_title("Bank credit depth vs income (orange: ASEAN; dashed: fitted)")
plt.show()
print("Credit gap vs the fitted line (percentage points of GDP):")
print(d.loc[d.index.isin(asean), "gap"].sort_values().round(0).rename(index=name).to_string())

# %% [markdown]
# ## 4. Logistics performance and manufacturing

# %%
cols = {"LP.LPI.OVRL.XQ": "Logistics performance (1-5)", "NV.IND.MANF.ZS": "Manufacturing (% of GDP)",
        "IT.NET.USER.ZS": "Internet users (%)"}
t = latest[latest["iso3"].isin(asean) & latest["indicator"].isin(cols)]
table = t.pivot(index="iso3", columns="indicator", values="latest_value").rename(columns=cols, index=name)
years = t.groupby("indicator")["latest_year"].max().rename(cols)
print(table.round(2).sort_values("Logistics performance (1-5)", ascending=False).to_string())
print("\nLatest years:", years.to_dict())

# %% [markdown]
# ## Takeaways
#
# - The scatter in section 1 separates fast-and-steady growers from volatile ones; the printed ranking names them.
# - Inflation spikes differ widely; compare the latest values printed in section 2.
# - The credit gap shows which economies have less bank lending than their income suggests: room for banks, or a
#   sign of constraints.
#
# **Limits**: some indicators (logistics performance, Gini) are published only every few years; values are
# revised by the World Bank; correlations here are descriptive, not causal.
