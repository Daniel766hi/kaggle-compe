# %% [markdown]
# # Fifty years of anime: what gets made, what gets loved
#
# This notebook explores **[Anime Database: 41k Titles, Scores & Studios](https://www.kaggle.com/datasets/danielaijdkx/anime-database-scores-studios-tags-franchises)**,
# built from the open anime-offline-database.
#
# **Questions answered**
# 1. How has anime production grown, and in which formats?
# 2. Which genres and themes are rising or fading?
# 3. Which studios score best, among those with enough titles?
# 4. Do sequels score better than the series that started them?
#
# The numbers in the text are computed from the data each time the notebook runs.

# %%
import glob
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

INK2, GRID, SURFACE = "#52514e", "#e6e5e0", "#fcfcfb"
TYPES = {"TV": "#2a78d6", "MOVIE": "#eb6834", "OVA": "#1baf7a", "ONA": "#e87ba4", "SPECIAL": "#c3c2b7"}
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


anime = pd.read_csv(find("anime.csv"))
studios = pd.read_csv(find("studios.csv"))
trends = pd.read_csv(find("tag_trends.csv"))
finished = anime[anime["status"] == "FINISHED"]
# A few titles marked finished carry future years; never treat the current or a later year as complete.
last = min(int(finished["year"].max()), pd.Timestamp.now().year)
print(f"{len(anime):,} anime; {anime['score'].notna().sum():,} with a score; latest complete year used: {last - 1}")

# %% [markdown]
# ## 1. Production by year and format

# %%
yr = finished[(finished["year"] >= 1975) & (finished["year"] <= last - 1)]
counts = yr.pivot_table(index="year", columns="type", values="anime_id", aggfunc="count").fillna(0)
counts = counts[[t for t in TYPES if t in counts]]
fig, ax = plt.subplots()
ax.stackplot(counts.index, counts.T.values, labels=counts.columns, colors=[TYPES[t] for t in counts.columns], alpha=0.9)
ax.set_ylabel("Titles first released"); ax.set_title("Anime released per year, by format"); ax.legend(loc="upper left")
plt.show()
peak = int(counts.sum(axis=1).idxmax())
share = counts.div(counts.sum(axis=1), axis=0) * 100
print(f"Peak year: {peak} with {int(counts.sum(axis=1)[peak]):,} titles. Share of TV series in {last - 1}: "
      f"{share.loc[last - 1, 'TV']:.0f}%; web releases (ONA): {share.loc[2010, 'ONA']:.0f}% in 2010 vs "
      f"{share.loc[last - 1, 'ONA']:.0f}% in {last - 1}.")

# %% [markdown]
# ## 2. Rising and fading themes
#
# Share of anime carrying each tag in the 2020s vs the 2010s, for tags on at least 200 titles. Meta tags such as
# "japanese production" or "present" are left out.

# %%
meta = {"japanese production", "present", "place", "time", "setting", "past", "future", "earth", "asia", "japan"}
t = trends[(trends["titles"] >= 200) & ~trends["tag"].isin(meta)].dropna(subset=["growth_2010s_to_2020s"])
t = t[t["share_2010s_pct"] >= 0.5]
show = pd.concat([t.nsmallest(8, "growth_2010s_to_2020s"), t.nlargest(12, "growth_2010s_to_2020s")]).sort_values("growth_2010s_to_2020s")
fig, ax = plt.subplots(figsize=(11, 7))
ax.barh(show["tag"], show["growth_2010s_to_2020s"], color=["#e34948" if g < 1 else "#1baf7a" for g in show["growth_2010s_to_2020s"]])
ax.axvline(1, color=INK2, lw=1); ax.set_xscale("log"); ax.grid(axis="y", visible=False)
ax.set_xlabel("Share in the 2020s / share in the 2010s (log scale; 1 = unchanged)")
ax.set_title("Themes gaining and losing ground")
plt.show()
top = t.nlargest(3, "growth_2010s_to_2020s")
print("Fastest-rising themes:", ", ".join(f"{r.tag} (x{r.growth_2010s_to_2020s:.1f})" for r in top.itertuples()))

# %% [markdown]
# ## 3. Studios: who scores best?
#
# Mean score of each studio's scored titles, for studios with at least 40 scored titles. A score here is the
# average across the anime sites that list a title, so it reflects mostly international fans.

# %%
s = studios[studios["scored_titles"] >= 40].sort_values("mean_score", ascending=False)
show = pd.concat([s.head(12), s.tail(5)]).iloc[::-1]
fig, ax = plt.subplots(figsize=(11, 7))
ax.barh(show["studio"], show["mean_score"], color="#6250d6")
for y, (v, b) in enumerate(zip(show["mean_score"], show["best_title"])):
    ax.text(v + 0.02, y, f"{v:.2f}  best: {b}" if isinstance(b, str) else f"{v:.2f}", va="center", fontsize=8, color=INK2)
ax.set_xlim(show["mean_score"].min() - 0.3, show["mean_score"].max() + 1.6); ax.grid(axis="y", visible=False)
ax.set_xlabel("Mean score (1-10)"); ax.set_title("Highest- and lowest-scoring studios (40+ scored titles)")
plt.show()
print(f"{len(s)} studios qualify; spread from {s['mean_score'].min():.2f} to {s['mean_score'].max():.2f}.")

# %% [markdown]
# ## 4. Do sequels score better?
#
# Within each TV franchise of two or more scored TV series, compare the first series with the later ones. Later
# entries are watched mostly by fans of the first, so a higher score is expected; the question is by how much.

# %%
tv = anime[(anime["type"] == "TV") & anime["score"].notna() & (anime["franchise_size"] >= 2) & anime["year"].notna()]
tv = tv.sort_values(["franchise_id", "year", "anime_id"])
tv["order"] = tv.groupby("franchise_id").cumcount()
first = tv[tv["order"] == 0].set_index("franchise_id")["score"]
later = tv[tv["order"] > 0].groupby("franchise_id")["score"].mean()
pair = pd.DataFrame({"first": first, "later": later}).dropna()
diff = pair["later"] - pair["first"]
fig, ax = plt.subplots()
ax.hist(diff, bins=np.arange(-3, 3.01, 0.2), color="#2a78d6")
ax.axvline(0, color=INK2, lw=1); ax.axvline(diff.median(), color="#e34948", lw=2)
ax.set_xlabel("Mean score of later TV series minus the first (points)"); ax.set_ylabel("Franchises")
ax.set_title("Sequels vs the series that started them (red: median)")
plt.show()
print(f"{len(pair)} franchises: later TV series score higher in {(diff > 0).mean():.0%} of them; "
      f"median difference {diff.median():+.2f} points.")

# %% [markdown]
# ## Takeaways
#
# - Production rose for decades; section 1 prints how the mix of formats (TV, web, OVA) has shifted.
# - Some themes are clearly rising in the 2020s; section 2 names them with their growth.
# - Studio averages differ by under two points; the best titles show what drives the top.
# - Later series in a franchise score only slightly better than the first, if at all: the share and median gap
#   printed in section 4 show how small the sequel effect is.
#
# **Limits**: scores come from the users of the source sites; obscure titles may have few ratings; franchises are
# grouped by related titles sharing a first word, which can split or miss a few series.
