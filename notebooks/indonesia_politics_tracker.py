# %% [markdown]
# # Indonesia's political pulse since October 2024: protests, conflict and cabinet changes
#
# This notebook explores **[Indonesia Politics Tracker: Events & Cabinet](https://www.kaggle.com/datasets/danielaijdkx/indonesian-political-moves-database-2024-2026)**,
# a daily-updated dataset of news events located in Indonesia (coded by the GDELT Project) and of
# every cabinet term since President Prabowo Subianto took office on 20 October 2024.
#
# **Questions answered**
# 1. How has protest activity evolved, and which periods stand out?
# 2. What did the biggest protest wave look like: when, where, and how violent?
# 3. Where in Indonesia do protests happen, relative to all reported events?
# 4. When was the cabinet reshuffled, and which posts changed most?
# 5. Were reshuffles preceded by unrest? A simple before/after comparison.
# 6. How much attention did the free meals programme (MBG) and the forest fires (karhutla) get, and when?
#
# > GDELT is machine-coded from news coverage. Counts are best read as **trends**, not exact
# > tallies, and every event links to a news article (`source_url`) that can be checked.

# %%
import glob
import os

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
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
pd.set_option("display.max_colwidth", 90)


def find(name):
    """Locate a dataset file on Kaggle (/kaggle/input) or locally (DATA_ROOT)."""
    for root in ("/kaggle/input", os.environ.get("DATA_ROOT", "../input")):
        hits = glob.glob(f"{root}/**/{name}", recursive=True)
        if hits:
            return hits[0]
    raise FileNotFoundError(name)


def note(ax, x, y, text, dx=20, dy=20):
    ax.annotate(text, (x, y), xytext=(dx, dy), textcoords="offset points", fontsize=9.5, color=INK,
                arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8),
                bbox=dict(boxstyle="round,pad=0.3", fc=SURFACE, ec=GRID))


# %%
events = pd.read_parquet(find("events.parquet"))
daily = pd.read_csv(find("daily_national.csv"), parse_dates=["date"])
by_province = pd.read_csv(find("daily_province.csv"), parse_dates=["date"])
cabinet = pd.read_csv(find("cabinet_positions.csv"), parse_dates=["start_date", "end_date"])
changes = pd.read_csv(find("cabinet_changes.csv"), parse_dates=["date"])
topics = pd.read_csv(find("daily_topics.csv"), parse_dates=["date"])
event_topics = pd.read_csv(find("event_topics.csv"), parse_dates=["date"])

# The most recent day is still being filled in by GDELT; leave it out of trends.
last_full_day = daily["date"].max() - pd.Timedelta(days=1)
daily = daily[daily["date"] <= last_full_day]
protests = events[(events["event_root_code"] == "14") & (events["date"] <= last_full_day)]
print(f"{len(events):,} events, {events['date'].min():%Y-%m-%d} to {events['date'].max():%Y-%m-%d}")
print(f"{len(protests):,} protest events; {len(cabinet)} cabinet terms; {len(changes)} appointments after the inauguration")
events.head(3)

# %% [markdown]
# ## 1. Protest activity over time
#
# Daily protest events (CAMEO root code 14: demonstrations, rallies, riots, strikes), smoothed
# with a 7-day average.

# %%
p7 = daily.set_index("date")["protests"].rolling(7, center=True, min_periods=4).mean()
peak_day = p7.idxmax()
fig, ax = plt.subplots()
ax.fill_between(p7.index, p7.values, color=C[0], alpha=0.15, lw=0)
ax.plot(p7.index, p7.values, color=C[0])
ax.set_title("Protest events per day in Indonesia (7-day average)")
ax.set_ylabel("events per day")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
note(ax, peak_day, p7.max(), f"Peak: week of {peak_day:%d %b %Y}\n{p7.max():.0f} protest events/day", dx=30, dy=-10)
plt.show()

monthly = protests.groupby(protests["date"].dt.to_period("M")).size()
typical = monthly.median()
print(f"Median month: {typical:.0f} protest events. Months with more than twice that:")
print(monthly[monthly > 2 * typical].to_string())

# %% [markdown]
# One period dwarfs everything else: the **late August to early September 2025** wave (the protests
# against new allowances for DPR members, which escalated after a delivery driver was killed by a
# police vehicle on 28 August). The printed list above shows which other months stood out.
#
# ## 2. Anatomy of the biggest wave
#
# Zoom in on the four weeks around the peak: protests per day, split into peaceful
# demonstrations and violent protest or riots, plus material conflict events (coercion,
# assault, fighting) reported in the same days.

# %%
start, end = peak_day - pd.Timedelta(days=14), peak_day + pd.Timedelta(days=14)
wave = protests[protests["date"].between(start, end)]
kind = np.where(wave["event"].str.contains("violent|riot", case=False, na=False), "violent protest / riot",
                "demonstration / other protest")
per_day = wave.assign(kind=kind).groupby(["date", "kind"]).size().unstack(fill_value=0)
conflict = daily.set_index("date").loc[start:end, "material_conflict"]

fig, ax = plt.subplots()
bottom = np.zeros(len(per_day))
for col, color in zip(["demonstration / other protest", "violent protest / riot"], [C[0], C[7]]):
    if col in per_day:
        ax.bar(per_day.index, per_day[col], bottom=bottom, color=color, width=0.8, label=col)
        bottom += per_day[col].values
ax.plot(conflict.index, conflict.values, color=INK2, lw=1.5, ls="--", label="material conflict events")
ax.set_title(f"The wave day by day, {start:%d %b} to {end:%d %b %Y}")
ax.set_ylabel("events per day")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
ax.legend(loc="upper left")
plt.show()

print("Provinces with the most protest events during the wave:")
print(wave["province"].value_counts().head(8).to_string())

# %% [markdown]
# The wave spread well beyond Jakarta (see the province list above), and the dashed line shows
# material conflict rising together with the protests.
#
# **Check the sources.** The most widely reported protest events of the wave, with the article
# GDELT coded them from:

# %%
(wave.sort_values("num_articles", ascending=False)
 [["date", "actor1_name", "event", "actor2_name", "province", "num_articles", "source_url"]]
 .head(8).reset_index(drop=True))

# %% [markdown]
# ## 3. Where protests happen
#
# Jakarta dominates the raw counts because it is the capital and the most-covered place in the
# news. A fairer comparison is the **share of a province's events that are protests**: how much
# of what gets reported from a province is protest.

# %%
prov = by_province[by_province["date"] <= last_full_day].groupby("province")[["events", "protests"]].sum()
prov = prov[prov["events"] >= 500]  # enough events for a stable share
prov["protest_share"] = prov["protests"] / prov["events"]
top = prov.sort_values("protest_share").tail(15)

fig, ax = plt.subplots(figsize=(11, 5.4))
ax.barh(top.index, top["protest_share"] * 100, color=C[0])
for y, (share, n) in enumerate(zip(top["protest_share"], top["protests"])):
    ax.text(share * 100 + 0.05, y, f"{share:.1%}  ({n:,} protests)", va="center", fontsize=9, color=INK2)
ax.set_title("Share of reported events that are protests, by province")
ax.set_xlabel("% of the province's events (provinces with at least 500 events)")
ax.set_xlim(0, top["protest_share"].max() * 100 * 1.35)
ax.grid(axis="y", visible=False)
plt.show()

# %%
geo = protests.dropna(subset=["latitude", "longitude"])
fig, ax = plt.subplots(figsize=(11, 4.4))
ax.scatter(events["longitude"], events["latitude"], s=1, color=MUTED, alpha=0.15, label="all events")
ax.scatter(geo["longitude"], geo["latitude"], s=6, color=C[7], alpha=0.35, label="protest events")
ax.set_xlim(94, 142)
ax.set_ylim(-11.5, 6.5)
ax.set_aspect("equal")
ax.set_title("Where events and protests were reported")
ax.legend(loc="lower left", markerscale=3)
ax.set_xticks([])
ax.set_yticks([])
ax.grid(False)
plt.show()

# %% [markdown]
# Even without a basemap the archipelago appears: Sumatra, Java, Bali and Nusa Tenggara,
# Kalimantan, Sulawesi and Papua. Many events sit on one point per city or province, because
# GDELT geocodes to the most specific place it can find in the article.
#
# ## 4. Cabinet changes
#
# `cabinet_changes` lists every appointment after the inauguration, with the previous holder.
# Days with several appointments are reshuffles.

# %%
per_date = changes.groupby("date").agg(appointments=("person", "size"),
                                       positions=("position", lambda s: "; ".join(s.head(4)) + (" ..." if len(s) > 4 else "")))
reshuffles = per_date[per_date["appointments"] >= 3]

fig, ax = plt.subplots(figsize=(11, 3.6))
ax.bar(per_date.index, per_date["appointments"], width=6,
       color=[C[1] if n >= 3 else MUTED for n in per_date["appointments"]])
ax.set_title("Appointments per day after the inauguration (orange: 3 or more, a reshuffle)")
ax.set_ylabel("appointments")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
plt.show()
print(f"{len(reshuffles)} days with 3 or more appointments:")
reshuffles

# %%
# Some posts have several holders at once (e.g. more than one deputy minister of finance), so
# turnover counts replacements: appointments that took over from a named previous holder.
replaced = changes.dropna(subset=["previous_holder"])
turnover = replaced.groupby("position").size().sort_values(ascending=False)
print(f"{len(replaced)} replacements across {turnover.size} positions. Positions replaced more than once:")
print(turnover[turnover > 1].to_string())
original = cabinet[(cabinet["start_date"] <= "2024-10-21") & cabinet["end_date"].isna()]
print(f"\n{len(original)} of the {(cabinet['start_date'] <= '2024-10-21').sum()} terms that began at the "
      "inauguration are still running.")

# %% [markdown]
# ## 5. Were reshuffles preceded by unrest?
#
# A simple event-study view: average protest events per day in the 30 days **before** and
# **after** each reshuffle day. This shows timing only; it cannot show that protests *caused* a
# reshuffle (or the other way round), and with only a handful of reshuffles any pattern is fragile.

# %%
series = daily.set_index("date")["protests"]
rows = []
for day in reshuffles.index:
    before = series.loc[day - pd.Timedelta(days=30): day - pd.Timedelta(days=1)]
    after = series.loc[day + pd.Timedelta(days=1): day + pd.Timedelta(days=30)]
    if len(before) >= 25 and len(after) >= 25:
        rows.append({"reshuffle": day.date(), "appointments": reshuffles.loc[day, "appointments"],
                     "protests/day, 30 days before": round(before.mean(), 1),
                     "protests/day, 30 days after": round(after.mean(), 1)})
study = pd.DataFrame(rows)
overall = series.mean()
print(f"Average over the whole period: {overall:.1f} protest events per day")
study

# %% [markdown]
# Compare each row with the overall average printed above: a reshuffle preceded by well above
# average protest activity is one that followed a period of unrest. Read the table together
# with section 2: the September 2025 reshuffles came right after the biggest protest wave in
# the data.
#
# ## 6. MBG and karhutla in the news
#
# `event_topics` tags events whose article is about a topic, recognised from words in its address
# (e.g. *free-meal*, *makan-bergizi*, *karhutla*, *wildfire*, *haze*). Monthly event counts work as
# an **attention index**: how much reported activity there was around each topic.

# %%
topics = topics[topics["date"] <= last_full_day]
month = topics.assign(month=topics["date"].dt.to_period("M").dt.to_timestamp())
attention = month.groupby(["month", "topic"])["events"].sum().unstack(fill_value=0)
labels = {"mbg": "Free meals (MBG)", "karhutla": "Forest fires & haze (karhutla)"}

fig, axes = plt.subplots(2, 1, figsize=(11, 6.4), sharex=True)
for ax, (topic, color) in zip(axes, [("mbg", C[2]), ("karhutla", C[1])]):
    series = attention[topic]
    ax.bar(series.index, series.values, width=25, color=color)
    ax.set_title(f"{labels[topic]}: events per month")
    peak = series.idxmax()
    note(ax, peak, series.max(), f"{peak:%b %Y}: {series.max():,} events", dx=-140 if topic == "karhutla" else 20, dy=-12)
axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
plt.tight_layout()
plt.show()

summary = month.groupby("topic").agg(events=("events", "sum"), protests=("protests", "sum"))
tone = topics.assign(w=topics["avg_tone"] * topics["articles"]).groupby("topic")[["w", "articles"]].sum()
summary["avg_tone"] = (tone["w"] / tone["articles"]).round(2)
summary["protest_share"] = (summary["protests"] / summary["events"]).round(3)
print("Overall average tone of all events:",
      round((daily["avg_tone"] * daily["articles"]).sum() / daily["articles"].sum(), 2))
summary.rename(index=lambda t: labels.get(t, t))

# %% [markdown]
# Two very different stories:
#
# - **MBG** is a steady presence in the news from its launch in January 2025, with several
#   surges rather than one peak. Its coverage is on average slightly *positive* (much of it
#   reports government announcements, visits and partnerships), even though its busiest
#   months coincide with trouble such as food-poisoning cases (see the articles below).
# - **Karhutla** is seasonal: quiet for most of the period, a smaller rise in mid-2025, then an
#   explosion in the 2026 dry season. Its coverage is far more negative than the national
#   average (compare `avg_tone` with the overall value printed above).
# - The **DPR allowance** topic is small but the most negative of all, and almost a third of its
#   events are protests: it is the issue behind the August 2025 wave.
#
# The most-reported articles in each topic's peak month, to see what drove the attention:

# %%
tagged = event_topics.merge(events[["event_id", "num_articles", "source_url", "province"]], on="event_id")
for topic in ["mbg", "karhutla"]:
    peak = attention[topic].idxmax()
    rows = tagged[(tagged["topic"] == topic) & (tagged["date"].dt.to_period("M") == peak.to_period("M"))]
    top_urls = (rows.groupby("source_url")["num_articles"].max().sort_values(ascending=False).head(5))
    print(f"\n{labels[topic]}, {peak:%B %Y}:")
    for url, n in top_urls.items():
        print(f"  {n:4d} articles  {url}")

# %%
fires = tagged[(tagged["topic"] == "karhutla") & (tagged["date"] >= "2026-07-01")]
print("Where the 2026 fire-season events were located (top provinces):")
print(fires["province"].value_counts().head(8).to_string())

# %% [markdown]
# Jakarta usually tops such lists because national decisions are reported from the capital;
# below it come the provinces where fires burned. For the fires themselves
# (burned area, hotspots, smoke), satellite data is the better source; the
# [Indonesia air quality](https://www.kaggle.com/datasets/danielaijdkx/indonesia-air-quality-hourly-pm25)
# dataset shows the smoke's effect on PM2.5 in cities such as Pekanbaru, Palembang and
# Palangka Raya.
#
# ## How to use this dataset well
#
# - **Trends, not tallies.** One real protest can appear as several GDELT events, and some
#   events are misclassified. Compare periods and provinces rather than quoting exact counts.
# - **Coverage bias.** Places and topics the media covers heavily are over-represented.
# - **Check a few sources.** `source_url` links each event to an article.
# - **Cabinet data** comes from the Wikipedia article on the cabinet (CC BY-SA 4.0), so it is
#   only as complete and current as that article.
#
# Ideas to take further: compare provinces' news tone (`avg_tone`), track a single actor
# (e.g. `actor1_type == "Police forces"`), or join with the
# [Indonesia air quality](https://www.kaggle.com/datasets/danielaijdkx/indonesia-air-quality-hourly-pm25)
# data to study the 2026 forest-fire season.
