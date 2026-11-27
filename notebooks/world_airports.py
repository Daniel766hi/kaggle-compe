# %% [markdown]
# # Airports of the world, and how far Indonesians are from a scheduled flight
#
# This notebook explores **[World Airports & Runways (OurAirports)](https://www.kaggle.com/datasets/danielaijdkx/world-airports-runways-ourairports)**.
#
# **Questions answered**
# 1. Which countries have the most airports with scheduled flights, and the longest runways?
# 2. How does an archipelago like Indonesia compare with large mainland countries?
# 3. Which Indonesian provinces depend on unpaved or short runways?
# 4. How far is each mapped airstrip in Indonesia from the nearest airport with scheduled flights?
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


airports = pd.read_csv(find("airports.csv"), keep_default_na=False, na_values=[""])
runways = pd.read_csv(find("runways.csv"))
countries = pd.read_csv(find("countries.csv"), keep_default_na=False, na_values=[""])
open_ = airports[airports["type"] != "closed"]
print(f"{len(airports):,} places, {open_['country_code'].nunique()} countries, {len(runways):,} runways")

# %% [markdown]
# ## 1. Where the scheduled airports are

# %%
top = countries.nlargest(20, "scheduled_airports").iloc[::-1]
fig, ax = plt.subplots(figsize=(11, 7))
ax.barh(top["country"], top["scheduled_airports"], color=["#eb6834" if c == "ID" else "#2a78d6" for c in top["country_code"]])
ax.set_xlabel("Open airports with scheduled airline service"); ax.grid(axis="y", visible=False)
ax.set_title("Countries with the most airports served by scheduled flights")
plt.show()
idn = countries.set_index("country_code").loc["ID"]
rank = int((countries["scheduled_airports"] > idn["scheduled_airports"]).sum()) + 1
print(f"Indonesia ranks #{rank} with {idn['scheduled_airports']} scheduled airports; longest runway "
      f"{idn['longest_runway_m']:,.0f} m at {idn['longest_runway_airport']}.")

# %% [markdown]
# ## 2. Indonesia's airports by province
#
# Airports with scheduled service and the share of their runways that are paved.

# %%
idn_a = open_[open_["country_code"] == "ID"]
rw = runways[~runways["closed"]].merge(idn_a[["airport_id", "region", "scheduled_service", "type"]], on="airport_id")
prov = pd.DataFrame({
    "scheduled": idn_a[idn_a["scheduled_service"]].groupby("region").size(),
    "all_open": idn_a.groupby("region").size(),
    "paved_pct": rw.groupby("region")["paved"].mean() * 100,
    "median_runway_m": rw.groupby("region")["length_m"].median(),
}).fillna({"scheduled": 0}).sort_values("scheduled")
fig, ax = plt.subplots(figsize=(11, 10))
ax.barh(prov.index, prov["all_open"], color=GRID, label="All open airports, airstrips and heliports")
ax.barh(prov.index, prov["scheduled"], color="#2a78d6", label="With scheduled flights")
ax.set_xlabel("Places"); ax.grid(axis="y", visible=False); ax.legend()
ax.set_title("Indonesia by province")
plt.show()
print("Provinces relying most on unpaved runways (share paved, median runway length):")
print(prov.sort_values("paved_pct").head(6)[["paved_pct", "median_runway_m", "all_open"]].round(0).to_string())

# %% [markdown]
# ## 3. How far to the nearest scheduled airport?
#
# For every open small airport and airstrip in Indonesia, the great-circle distance to the nearest airport with
# scheduled flights. Remote airstrips (often in Papua) are the only air link for many communities.

# %%
def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(a))


hubs = idn_a[idn_a["scheduled_service"]]
strips = idn_a[(idn_a["type"] == "small_airport") & ~idn_a["scheduled_service"]].copy()
d = haversine(strips["latitude"].to_numpy()[:, None], strips["longitude"].to_numpy()[:, None],
              hubs["latitude"].to_numpy()[None, :], hubs["longitude"].to_numpy()[None, :])
strips["km_to_scheduled"] = d.min(axis=1)
fig, ax = plt.subplots()
ax.hist(strips["km_to_scheduled"], bins=40, color="#2a78d6")
ax.set_xlabel("Distance to the nearest airport with scheduled flights (km)"); ax.set_ylabel("Airstrips")
ax.set_title("Indonesian airstrips: distance to scheduled service")
plt.show()
print(f"{len(strips):,} airstrips without scheduled service; median distance {strips['km_to_scheduled'].median():.0f} km; "
      f"{(strips['km_to_scheduled'] > 100).mean():.0%} are more than 100 km away.")
print(strips.groupby("region")["km_to_scheduled"].agg(["size", "median"]).sort_values("size", ascending=False).head(6).round(0).to_string())

# %% [markdown]
# ## Takeaways
#
# - Section 1 shows where Indonesia ranks among countries for airports with scheduled flights.
# - Unpaved and short runways concentrate in a few provinces, which limits the aircraft that can serve them.
# - Most Indonesian airstrips sit within reach of a scheduled airport, but a tail of remote strips is far from one.
#
# **Limits**: OurAirports is volunteer-maintained; small strips may be missing or out of date; distances are straight
# lines, not travel routes.
