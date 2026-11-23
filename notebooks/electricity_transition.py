# %% [markdown]
# # Who still runs on coal? The power transition in 220 countries
#
# This notebook explores **[Global Electricity Mix: Coal, Gas, Solar, Wind](https://www.kaggle.com/datasets/danielaijdkx/global-electricity-mix-generation-emissions)**,
# Ember's yearly and monthly electricity data.
#
# **Questions answered**
# 1. How has the world's power mix changed since 2000?
# 2. Where does ASEAN stand, and how does Indonesia compare with its neighbours?
# 3. Which countries are adding solar and wind fastest?
# 4. Does a cleaner mix really mean a lower carbon intensity?
#
# The numbers in the text are computed from the data each time the notebook runs.

# %%
import glob
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e6e5e0", "#fcfcfb"
FUEL = {"Coal": "#52514e", "Gas": "#eda100", "Other fossil": "#b8860b", "Nuclear": "#6250d6", "Hydro": "#2a78d6",
        "Wind": "#1baf7a", "Solar": "#f2c14e", "Bioenergy": "#008300", "Other renewables": "#9ad0c2"}
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


yearly = pd.read_csv(find("electricity_yearly.csv"))
summary = pd.read_csv(find("country_summary.csv"))
areas = pd.read_csv(find("areas.csv"))
singles = yearly[~yearly["is_aggregate"]]
last = int(summary["year"].max())
print(f"{yearly['area'].nunique()} areas, {yearly['year'].min()}-{yearly['year'].max()}; latest full year {last}")

# %% [markdown]
# ## 1. The world's power mix since 2000

# %%
world = singles[(singles["area"] == "World") & (singles["year"] >= 2000)].pivot_table(index="year", columns="source", values="share_pct")
world = world[[c for c in FUEL if c in world]]
fig, ax = plt.subplots()
ax.stackplot(world.index, world.T.values, labels=world.columns, colors=[FUEL[c] for c in world.columns], alpha=0.9)
ax.set_ylim(0, 100); ax.set_ylabel("% of world generation")
ax.set_title("World electricity generation by source (%)")
ax.legend(loc="upper left", bbox_to_anchor=(1, 1))
plt.show()
w = yearly[(yearly["area"] == "World")].pivot_table(index="year", columns="source", values="share_pct")
print(f"Coal: {w.loc[2000, 'Coal']:.1f}% in 2000 -> {w.loc[last, 'Coal']:.1f}% in {last}. "
      f"Wind and solar: {w.loc[2000, 'Wind and solar']:.1f}% -> {w.loc[last, 'Wind and solar']:.1f}%. "
      f"Clean (renewables + nuclear): {w.loc[2000, 'Clean']:.1f}% -> {w.loc[last, 'Clean']:.1f}%.")

# %% [markdown]
# ## 2. ASEAN: Indonesia and its neighbours
#
# The latest year's mix for each ASEAN member Ember covers, sorted by coal share.

# %%
asean = set(areas.loc[areas["asean"], "area"])
s = summary[summary["area"].isin(asean)].sort_values("coal_pct")
cols = ["coal_pct", "gas_pct", "hydro_pct", "wind_solar_pct"]
names = {"coal_pct": "Coal", "gas_pct": "Gas", "hydro_pct": "Hydro", "wind_solar_pct": "Wind + solar"}
fig, ax = plt.subplots(figsize=(11, 0.5 * len(s) + 1.2))
left = np.zeros(len(s))
for c in cols:
    ax.barh(s["area"], s[c].fillna(0), left=left, label=names[c], color=FUEL[{"Wind + solar": "Solar"}.get(names[c], names[c])])
    left += s[c].fillna(0).to_numpy()
ax.barh(s["area"], 100 - left, left=left, label="Other", color=GRID)
ax.set_xlim(0, 100); ax.set_xlabel("% of generation"); ax.grid(axis="y", visible=False)
ax.set_title(f"ASEAN power mix, {last}")
ax.legend(ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.12))
plt.show()
print(s[["area", "generation_twh", "coal_pct", "clean_pct", "clean_pct_change_5y", "intensity_gco2e_kwh"]].round(1).to_string(index=False))

# %% [markdown]
# ## 3. Who is adding solar and wind fastest?
#
# Change in the wind-and-solar share over five years, among countries generating at least 20 TWh a year.

# %%
ws = yearly[(yearly["source"] == "Wind and solar") & yearly["area"].isin(summary["area"])].pivot_table(index="area", columns="year", values="share_pct")
big = summary.loc[summary["generation_twh"] >= 20, "area"]
gain = (ws[last] - ws[last - 5]).reindex(big).dropna().sort_values()
show = pd.concat([gain.head(5), gain.tail(15)])
fig, ax = plt.subplots(figsize=(11, 7))
ax.barh(show.index, show.values, color=["#e34948" if v < 0 else "#1baf7a" for v in show.values])
for name in ("Indonesia", "Vietnam", "Viet Nam", "Philippines", "Thailand", "Malaysia"):
    if name in gain:
        print(f"{name}: {gain[name]:+.1f} percentage points in five years (rank {int((gain > gain[name]).sum()) + 1} of {len(gain)})")
ax.set_xlabel(f"Change in wind + solar share, {last - 5}-{last} (percentage points)")
ax.set_title("Fastest and slowest movers in wind and solar"); ax.grid(axis="y", visible=False)
plt.show()

# %% [markdown]
# ## 4. Cleaner mix, lower carbon intensity?

# %%
s = summary.dropna(subset=["clean_pct", "intensity_gco2e_kwh"])
s = s[s["generation_twh"] >= 5]
fig, ax = plt.subplots(figsize=(11, 6))
ax.scatter(s["clean_pct"], s["intensity_gco2e_kwh"], s=np.sqrt(s["generation_twh"]) * 6, color="#2a78d6", alpha=0.5)
for name in ("China", "India", "United States", "Indonesia", "France", "Brazil", "Poland", "Vietnam", "Viet Nam", "Japan"):
    r = s[s["area"] == name]
    if len(r):
        ax.annotate(name, (r["clean_pct"].iloc[0], r["intensity_gco2e_kwh"].iloc[0]), fontsize=9, xytext=(4, 4), textcoords="offset points")
ax.set_xlabel("Clean share of generation (%)"); ax.set_ylabel("Carbon intensity (gCO2e/kWh)")
ax.set_title(f"Clean share vs carbon intensity, {last} (bubble = generation)")
plt.show()
r = np.corrcoef(s["clean_pct"], s["intensity_gco2e_kwh"])[0, 1]
print(f"Correlation between clean share and carbon intensity: {r:.2f} across {len(s)} countries.")
coal_heavy = s[s["coal_pct"] >= 50]
print(f"Countries above 50% coal: {len(coal_heavy)}; their median intensity is {coal_heavy['intensity_gco2e_kwh'].median():.0f} gCO2e/kWh "
      f"vs {s['intensity_gco2e_kwh'].median():.0f} for all.")

# %% [markdown]
# ## Takeaways
#
# - The printed figures above show how far coal's share has moved since 2000 and how much of the gain came from
#   wind and solar.
# - Within ASEAN the mixes differ widely: compare coal share and the 5-year change in the clean share in the table.
# - Clean share and carbon intensity are strongly linked, but the coal share explains much of the spread:
#   replacing coal matters more than adding renewables on top of gas.
#
# **Limits**: Ember's emissions are lifecycle estimates; monthly data covers only larger economies; recent years
# are revised as national statistics are finalized.
