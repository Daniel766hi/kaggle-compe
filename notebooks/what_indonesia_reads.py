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
# Spikes whose views vanish the next day (below 1% of the spike day) are almost always automated
# traffic; the dataset flags them as `one_day_burst`. They are left out here.
spikes_all = spikes
spikes = spikes[~(spikes["views_p1"] < 0.01 * spikes["views_d0"])].reset_index(drop=True)
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
yearly_views = totals.groupby(totals["date"].dt.year)["views"].mean() / 1e6
print("Average daily views (millions) per year:", yearly_views.round(2).to_dict())
last12 = totals[totals["date"] > totals["date"].max() - pd.Timedelta(days=365)]["views"].mean() / 1e6
peak_year = yearly_views.idxmax()
print(f"Last 12 months: {last12:.2f} million a day, {1 - last12 / yearly_views[peak_year]:.0%} below {peak_year} "
      f"and {1 - last12 / yearly_views[2024]:.0%} below 2024")
share = (totals["views_mobile_web"] + totals["views_mobile_app"]).sum() / totals["views"].sum()
print(f"Phones (browser + app): {share:.0%} of all views since 2015")

# %% [markdown]
# Readership peaked in 2020 (people at home during COVID-19) and has fallen steeply since 2024. The
# data alone cannot say why; a likely part of it is people getting answers from search-engine
# summaries and AI chatbots without opening Wikipedia.

# %% [markdown]
# ## 2. The articles of each year
#
# Ranked by the number of days each article was in the daily **top 100**: a measure of steady
# attention. (Summed views would put a few pages with huge bursts of automated traffic, such as
# search-engine names, on top.)

# %%
top100 = art[art["rank"] <= 100]
yearly = top100.groupby(["year", "title"]).size().rename("days_in_top_100").reset_index()
best = yearly.sort_values(["year", "days_in_top_100"], ascending=[True, False]).groupby("year").head(5)
best["rank"] = best.groupby("year").cumcount() + 1
best.pivot(index="rank", columns="year", values="title")

# %% [markdown]
# And the biggest single day of each year. To keep out automated traffic, a day only counts when the
# article kept at least 10% of those views the next day (real attention fades, it does not vanish).

# %%
nxt = art[["article", "date", "views"]].assign(date=art["date"] - pd.Timedelta(days=1)).rename(columns={"views": "next_day"})
clean = art.merge(nxt, on=["article", "date"], how="left")
clean = clean[clean["next_day"] >= 0.1 * clean["views"]]
peaks = clean.loc[clean.groupby("year")["views"].idxmax(), ["year", "date", "title", "views", "next_day"]]
peaks.assign(date=peaks["date"].dt.strftime("%d %b")).reset_index(drop=True)

# %% [markdown]
# Most peaks are real news (Habibie's death in 2019, Didi Kempot's in 2020, the World Cup final
# stretch in 2022). A few names, such as Facebook in 2015 and Yandex in 2023, are most likely
# automated traffic that lasted several days: the filter above only removes one-day bursts.
#
# ## 3. What comes back every year
#
# Some topics return with the calendar: national days, religious holidays, exams. Below, articles whose
# busiest two weeks of the year fell in the **same** two weeks in at least 6 different years. (Articles
# named after a date, such as "17 Agustus", are left out: the main page features them on their date.)

# %%
r = art[~art["title"].str.match(r"^\d{1,2} \w+$")].copy()
r["fortnight"] = (r["date"].dt.dayofyear - 1) // 14
per_year = r.groupby(["article", "year", "fortnight"])["views"].sum().reset_index()
busiest = per_year.loc[per_year.groupby(["article", "year"])["views"].idxmax()]
same = busiest.groupby(["article", "fortnight"]).size().rename("years").reset_index()
same = same[same["years"] >= 6].sort_values("years", ascending=False).drop_duplicates("article")
same["around"] = pd.to_datetime(same["fortnight"] * 14 + 7, unit="D", origin="2025-01-01").dt.strftime("%d %b")
same["views in top lists"] = same["article"].map(r.groupby("article")["views"].sum())
same.assign(article=same["article"].str.replace("_", " ")).nlargest(15, "views in top lists")[
    ["article", "years", "around", "views in top lists"]].reset_index(drop=True)

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
# - Indonesian Wikipedia is read mostly on phones, and readership has fallen steeply since 2024.
# - Yearly favourites mix evergreen school topics (sports, the constitution, independence) with that
#   year's big news; a few pages are inflated by automated traffic, so rank by steady attention.
# - The national calendar is visible every year: Independence Day in August, G30S on 1 October,
#   Sumpah Pemuda on 28 October, Kartini in April, and sports topics in the December exam season.
# - Attention spikes fade fast and fairly predictably; the [attention-decay model](https://www.kaggle.com/models/danielaijdkx/wikipedia-attention-decay-forecast)
#   forecasts the 7 days after a spike.
#
# Data: Wikimedia Foundation pageviews API (CC0).
