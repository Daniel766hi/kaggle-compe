# %% [markdown]
# # What Indonesia reads: 11 years of Wikipedia attention
#
# This notebook explores **[What Indonesia Reads: Wikipedia Top 1000 Daily](https://www.kaggle.com/datasets/danielaijdkx/indonesian-wikipedia-daily-top-articles)**:
# the 1,000 most-viewed pages of Indonesian Wikipedia every day since July 2015, updated daily.
#
# **Questions answered**
# 1. How much is Indonesian Wikipedia read, and how has that changed (desktop vs mobile)?
# 2. What were the most-read articles of each year?
# 3. What keeps coming back every year (Ramadan, Independence Day, exams)?
# 4. When something suddenly becomes news, how fast does the attention fade?

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
top = pd.read_parquet(find("top_articles.parquet"))
totals = pd.read_csv(find("daily_totals.csv"), parse_dates=["date"])
spikes = pd.read_csv(find("attention_spikes.csv"), parse_dates=["spike_date"])
art = top[top["is_article"]].copy()
art["year"] = art["date"].dt.year
art["title"] = art["article"].str.replace("_", " ", regex=False)
print(f"{top['date'].nunique():,} daily top lists, {top['date'].min():%d %b %Y} to {top['date'].max():%d %b %Y}; "
      f"{art['article'].nunique():,} different articles reached a top 1,000; {len(spikes):,} attention spikes")

# %% [markdown]
# ## 1. How much is Indonesian Wikipedia read?

# %%
monthly = totals.set_index("date").resample("MS").mean()
fig, ax = plt.subplots()
ax.stackplot(monthly.index, monthly["views_mobile_web"] / 1e6, monthly["views_desktop"] / 1e6,
             monthly["views_mobile_app"] / 1e6, labels=["mobile browser", "desktop", "Wikipedia app"],
             colors=[C[0], C[1], C[2]], alpha=0.85)
ax.set_ylabel("Daily views (millions, monthly average)")
ax.set_title("Indonesian Wikipedia: daily views by people, by device")
ax.legend(loc="upper right")
plt.show()
first, last = monthly.iloc[12], monthly.iloc[-2]
print(f"Mobile share: {first['views_mobile_web'] / first['views']:.0%} in {monthly.index[12]:%Y} -> "
      f"{last['views_mobile_web'] / last['views']:.0%} in {monthly.index[-2]:%b %Y}")

# %% [markdown]
# ## 2. The most-read articles of each year
#
# Views summed over the days an article was in the daily top 1,000 (a lower bound for its total).

# %%
yearly = art.groupby(["year", "title"])["views"].sum().reset_index()
best = yearly.sort_values(["year", "views"], ascending=[True, False]).groupby("year").head(5)
best["rank"] = best.groupby("year").cumcount() + 1
best.pivot(index="rank", columns="year", values="title")

# %% [markdown]
# ## 3. What comes back every year
#
# Some topics return on the calendar: holidays, national days, exams. Here, a few recurring
# articles' daily views (when in the top 1,000) by day of the year, averaged over all years.

# %%
recurring = art.groupby("article")["year"].nunique()
recurring = recurring[recurring >= 8].index
r = art[art["article"].isin(recurring)].copy()
r["doy"] = r["date"].dt.dayofyear
# Articles whose attention is concentrated in a few weeks of the year.
conc = r.groupby("article").apply(lambda g: g.groupby(g["doy"] // 14)["views"].sum().max() / g["views"].sum(),
                                  include_groups=False)
seasonal = conc[conc > 0.5].sort_values(ascending=False).head(12)
pd.DataFrame({"title": [a.replace("_", " ") for a in seasonal.index],
              "share of its views in its busiest 2 weeks": seasonal.round(2).to_numpy(),
              "peak date (typical)": [r[r["article"] == a].groupby("doy")["views"].mean().idxmax() for a in seasonal.index]}
             ).assign(**{"peak date (typical)": lambda d: pd.to_datetime(d["peak date (typical)"] - 1, unit="D",
                                                                          origin="2025-01-01").dt.strftime("%d %b")})

# %% [markdown]
# ## 4. How fast does attention fade?
#
# An *attention spike* is an article that jumps into the day's top 100 after a week outside the top
# 1,000. For each spike the dataset holds its daily views from a week before to two weeks after.

# %%
cols = [f"views_m{k}" for k in range(7, 0, -1)] + ["views_d0"] + [f"views_p{k}" for k in range(1, 15)]
offsets = list(range(-7, 15))
rel = spikes[cols].div(spikes["views_d0"].clip(lower=1), axis=0)
fig, ax = plt.subplots()
ax.fill_between(offsets, rel.quantile(0.25), rel.quantile(0.75), color=C[0], alpha=0.2, label="middle half of spikes")
ax.plot(offsets, rel.median(), color=C[0], marker="o", ms=4, label="median spike")
ax.set_xlabel("Days from the spike day")
ax.set_ylabel("Views, as a share of the spike day")
ax.set_title("The typical attention spike: a sharp peak, most of it gone within a few days")
ax.legend()
plt.show()
print("Median share of the spike-day views kept:",
      {f"day +{h}": f"{rel[f'views_p{h}'].median():.0%}" for h in (1, 2, 3, 7, 14)})
print(f"Median half-life: {spikes['half_life_days'].median():.0f} day(s); "
      f"{spikes['half_life_days'].isna().mean():.0%} of spikes had not halved within 14 days")

# %% [markdown]
# Not every spike fades at the same speed. Spikes that grow over several days (a developing
# story) tend to last longer than ones that appear from nothing in a single day.

# %%
spikes["rise"] = np.where(spikes["views_m1"] >= spikes["views_d0"] * 0.2, "already rising the day before",
                          "out of nowhere")
kept = spikes.assign(kept_day3=spikes["views_p3"] / spikes["views_d0"].clip(lower=1))
kept.groupby("rise")["kept_day3"].describe()[["count", "25%", "50%", "75%"]].round(2)

# %% [markdown]
# ## The biggest spikes

# %%
spikes.nlargest(15, "views_d0")[["spike_date", "title", "spike_rank", "views_d0", "next_7d", "half_life_days"]] \
    .reset_index(drop=True)

# %% [markdown]
# ## Takeaways
#
# - Indonesian Wikipedia is read mostly on phones, and the overall level is in the chart above.
# - Yearly favourites mix evergreen topics with that year's big news.
# - Calendar topics come back every year at the same time, a useful seasonal signal.
# - Attention spikes fade fast and fairly predictably; the [attention-decay model](https://www.kaggle.com/models/danielaijdkx/wikipedia-attention-decay-forecast)
#   forecasts the 7 days after a spike.
#
# Data: Wikimedia Foundation pageviews API (CC0).
