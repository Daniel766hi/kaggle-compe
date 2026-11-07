# %% [markdown]
# # Global supply chains from space: chokepoints, the Red Sea crisis and Indonesia's trade
#
# This notebook explores **[Global Supply Chain Monitor: Ports & Chokepoints](https://www.kaggle.com/datasets/danielaijdkx/global-supply-chain-monitor-ports-chokepoints)**:
# the IMF's daily estimates of port calls and trade volumes for 190+ countries and of ship transits
# through 28 straits and canals (from satellite ship tracking), plus the New York Fed's Global Supply
# Chain Pressure Index (GSCPI).
#
# **Questions answered**
# 1. How stressed are global supply chains, and how does today compare with 2021?
# 2. What did the Red Sea crisis do to shipping routes?
# 3. How busy are Indonesia's straits (Malacca, Sunda, Lombok, Makassar)?
# 4. How is Indonesia's seaborne trade doing, compared with its neighbours?
# 5. Which Indonesian ports matter most, and for what?

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
    """Locate a dataset file on Kaggle (/kaggle/input) or locally (DATA_ROOT)."""
    for root in ("/kaggle/input", os.environ.get("DATA_ROOT", "../input")):
        hits = glob.glob(f"{root}/**/{name}", recursive=True)
        if hits:
            return hits[0]
    raise FileNotFoundError(name)


# %%
country = pd.read_parquet(find("country_daily.parquet"))
choke = pd.read_csv(find("chokepoint_daily.csv"), parse_dates=["date"])
ports = pd.read_csv(find("ports.csv"))
gscpi = pd.read_csv(find("gscpi.csv"), parse_dates=["month"])
monthly = pd.read_csv(find("country_monthly.csv"), parse_dates=["month"])
print(f"Country data {country['date'].min():%d %b %Y} to {country['date'].max():%d %b %Y}; "
      f"chokepoints to {choke['date'].max():%d %b %Y}; GSCPI to {gscpi['month'].max():%B %Y}")

# %% [markdown]
# ## 1. Supply chain pressure, 1998 to now
#
# The GSCPI combines shipping costs, delivery times, backlogs and inventories into one number:
# 0 is normal, +1 is one standard deviation of extra pressure.

# %%
fig, ax = plt.subplots()
ax.fill_between(gscpi["month"], gscpi["gscpi"], 0, where=gscpi["gscpi"] > 0, color=C[7], alpha=0.35, lw=0)
ax.fill_between(gscpi["month"], gscpi["gscpi"], 0, where=gscpi["gscpi"] <= 0, color=C[0], alpha=0.35, lw=0)
ax.plot(gscpi["month"], gscpi["gscpi"], color=INK, lw=1.2)
peak = gscpi.loc[gscpi["gscpi"].idxmax()]
last = gscpi.iloc[-1]
ax.annotate(f"peak {peak['gscpi']:.1f} ({peak['month']:%b %Y})", (peak["month"], peak["gscpi"]), xytext=(20, -10),
            textcoords="offset points", fontsize=9.5)
ax.annotate(f"{last['gscpi']:+.2f} ({last['month']:%b %Y})", (last["month"], last["gscpi"]), xytext=(-110, 25),
            textcoords="offset points", fontsize=9.5, arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
ax.axhline(0, color=INK2, lw=0.8)
ax.set_title("Global Supply Chain Pressure Index (New York Fed)")
ax.set_ylabel("standard deviations from average")
plt.show()
print("Last 6 months:", gscpi.tail(6).set_index(gscpi.tail(6)["month"].dt.strftime("%b %Y"))["gscpi"].round(2).to_dict())

# %% [markdown]
# ## 2. The Red Sea crisis: ships go around Africa
#
# From late 2023, attacks on shipping near Yemen made many ships avoid the Bab el-Mandeb Strait and the
# Suez Canal and sail around the Cape of Good Hope instead (two weeks longer to Europe).

# %%
pick = ["Suez Canal", "Bab el-Mandeb Strait", "Cape of Good Hope"]
weekly = (choke[choke["chokepoint"].isin(pick)].set_index("date").groupby("chokepoint")["transits"]
          .resample("W").mean().unstack(0))
fig, ax = plt.subplots()
for name, color in zip(pick, [C[0], C[7], C[2]]):
    ax.plot(weekly.index, weekly[name], color=color, label=name)
ax.axvline(pd.Timestamp("2023-11-19"), color=INK2, lw=0.8, ls="--")
ax.text(pd.Timestamp("2023-12-05"), weekly.max().max() * 0.95, "first attacks\nNov 2023", fontsize=9, color=INK2)
ax.set_ylabel("ships per day (weekly average)")
ax.set_title("Transits per day: the Red Sea route emptied, the Cape route filled")
ax.legend(loc="upper left")
plt.show()
before = choke[(choke["date"] >= "2023-01-01") & (choke["date"] < "2023-11-01")].groupby("chokepoint")["transits"].mean()
recent = choke[choke["date"] > choke["date"].max() - pd.Timedelta(days=90)].groupby("chokepoint")["transits"].mean()
print("Ships per day, Jan-Oct 2023 vs the last 90 days:")
print(pd.DataFrame({"2023": before[pick], "last 90 days": recent[pick],
                    "change %": ((recent[pick] / before[pick] - 1) * 100)}).round(1).to_string())

# %% [markdown]
# ## 3. Indonesia's straits
#
# The Malacca Strait is one of the busiest waterways in the world; ships too large for it, or heading for
# Australia, use the Sunda, Lombok and Makassar straits.

# %%
idn_straits = ["Malacca Strait", "Sunda Strait", "Lombok Strait", "Makassar Strait", "Ombai Strait"]
m = (choke[choke["chokepoint"].isin(idn_straits)].assign(month=lambda d: d["date"].dt.to_period("M").dt.to_timestamp())
     .groupby(["month", "chokepoint"])["transits"].mean().unstack())
m = m[m.index < choke["date"].max().to_period("M").to_timestamp()]  # complete months only
fig, axes = plt.subplots(1, 2, figsize=(13, 4.4))
axes[0].plot(m.index, m["Malacca Strait"], color=C[0])
axes[0].set_title("Malacca Strait: ships per day")
for name, color in zip(idn_straits[1:], C[1:]):
    axes[1].plot(m.index, m[name], color=color, label=name)
axes[1].set_title("The other Indonesian straits")
axes[1].legend(fontsize=9)
plt.show()
mix = choke[(choke["chokepoint"] == "Malacca Strait") & (choke["date"].dt.year == choke["date"].max().year - 1)]
shares = mix[[f"transits_{v}" for v in ["container", "dry_bulk", "general_cargo", "roro", "tanker"]]].sum()
jump = m["Malacca Strait"]
print(f"Malacca: {jump['2021-06':'2021-07'].mean():.0f} ships a day in mid-2021, {jump['2022-01':'2022-02'].mean():.0f} "
      "in early 2022.")
print(f"Malacca Strait {choke['date'].max().year - 1}: {mix['transits'].mean():.0f} ships a day;",
      (shares / shares.sum()).rename(lambda c: c.replace("transits_", "")).map("{:.0%}".format).to_dict())

# %% [markdown]
# **A caution about late 2021**: Malacca traffic jumps by about a third within a few months, and
# Indonesia's trade volumes (next section) step up at the same time. A change that sudden is more
# likely an improvement in satellite ship tracking than real traffic, so compare years from 2022
# onward, or look at changes rather than levels across that date.
#
# ## 4. Indonesia's seaborne trade and its neighbours
#
# Monthly imports plus exports by sea (metric tons), and the change from a year earlier.

# %%
peers = {"IDN": "Indonesia", "MYS": "Malaysia", "SGP": "Singapore", "THA": "Thailand", "VNM": "Viet Nam",
         "PHL": "Philippines"}
mm = monthly[monthly["iso3"].isin(peers)].copy()
mm["trade_mt"] = (mm["import"] + mm["export"]) / 1e6
fig, axes = plt.subplots(1, 2, figsize=(13, 4.4))
idn = mm[mm["iso3"] == "IDN"]
axes[0].bar(idn["month"], idn["export"] / 1e6, width=25, color=C[2], label="exports")
axes[0].bar(idn["month"], idn["import"] / 1e6, width=25, bottom=idn["export"] / 1e6, color=C[0], label="imports")
axes[0].set_title("Indonesia: seaborne trade (million tons a month)")
axes[0].legend(loc="upper left")
for (iso, g), color in zip(mm.groupby("iso3"), C):
    roll = g.set_index("month")["trade_yoy_pct"].rolling(3).mean()
    axes[1].plot(roll.index, roll, color=color, lw=2.6 if iso == "IDN" else 1.2, label=peers[iso])
axes[1].axhline(0, color=INK2, lw=0.8)
axes[1].set_ylim(-40, 60)
axes[1].set_title("Change vs a year earlier (%, 3-month average)")
axes[1].legend(fontsize=8.5, ncol=2)
plt.show()
latest = idn.dropna(subset=["trade_yoy_pct"]).tail(1).iloc[0]
print(f"Indonesia {latest['month']:%B %Y}: exports {latest['export'] / 1e6:.1f} Mt, imports {latest['import'] / 1e6:.1f} Mt, "
      f"total {latest['trade_yoy_pct']:+.1f}% vs a year earlier. Exports are about "
      f"{idn['export'].sum() / idn['import'].sum():.1f}x imports by weight.")

# %% [markdown]
# ## 5. Indonesia's ports

# %%
idn_ports = ports[ports["iso3"] == "IDN"].sort_values("vessels_total", ascending=False)
fig, ax = plt.subplots(figsize=(12, 5))
size = idn_ports["vessels_total"] / idn_ports["vessels_total"].max() * 600
ax.scatter(idn_ports["longitude"], idn_ports["latitude"], s=size, color=C[0], alpha=0.5, lw=0)
for r in idn_ports.head(10).itertuples():
    ax.annotate(r.port, (r.longitude, r.latitude), xytext=(4, 4), textcoords="offset points", fontsize=8.5)
ax.set_aspect("equal")
ax.set_title(f"{len(idn_ports)} Indonesian ports tracked by PortWatch (size = ships per year)")
plt.show()
by_export = idn_ports.nlargest(5, "share_of_country_exports")
print("Largest shares of Indonesia's seaborne exports:",
      dict(zip(by_export["port"], by_export["share_of_country_exports"].map("{:.0f}%".format))))
idn_ports.head(12)[["port", "vessels_total", "vessels_container", "vessels_tanker", "industry_1",
                    "share_of_country_exports", "share_of_country_imports"]].reset_index(drop=True)

# %% [markdown]
# ## Takeaways
#
# - Supply chain pressure is far below the 2021 peak, but the GSCPI shows how quickly it can rise.
# - The Red Sea crisis rerouted world shipping: Suez and Bab el-Mandeb traffic fell sharply and the Cape
#   of Good Hope took the ships, at the cost of longer voyages.
# - The Malacca Strait carries a large share of world trade; the Indonesian straits are its alternatives.
# - Indonesia exports about twice as much by weight as it imports, and its biggest export ports
#   (Banjarmasin, Samarinda) are Kalimantan bulk ports handling mineral products, so its seaborne trade
#   follows commodity demand. Jakarta's Tanjung Priok dominates imports and container traffic.
# - PortWatch's levels shift in late 2021, most likely with better ship tracking: trends across that date
#   need care.
#
# Data: IMF PortWatch (cite "IMF PortWatch"); Global Supply Chain Pressure Index, Federal Reserve Bank of
# New York.
