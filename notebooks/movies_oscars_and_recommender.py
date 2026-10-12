# %% [markdown]
# # Predicting Best Picture, and a "more like this" movie recommender
#
# This notebook uses **[Movie Metadata: Genre, Crew, Color & Tech Specs](https://www.kaggle.com/datasets/danielaijdkx/movie-metadata-genre-crew-color-tech-specs)**,
# a weekly-updated table of about 26,000 notable films from Wikidata (genres, directors, writers,
# cast, color, aspect ratio, runtime, box office, critic scores and award nominations).
#
# **Part A: Oscars**
# 1. Which films will be nominated for Best Picture? A model that only uses information known
#    *before* the nominations, tested year by year on films it never saw.
# 2. A blind test on the 2026 ceremony (films released in 2025).
# 3. A forecast for films released in 2026 (the ceremony in early 2027).
# 4. Who wins? How far a simple rule gets you, and why early-season winner calls are mostly guesses.
#
# **Part B: fan recommendations.** A content-based recommender ("you liked *Inception*, try ...")
# that explains each suggestion: same director, same composer, shared genres.
#
# > The data is refreshed every week, so the forecast in section A3 changes as new 2026 films
# > get Wikipedia articles and as critic scores and awards are added on Wikidata.

# %%
import glob
import os
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler, normalize

warnings.filterwarnings("ignore", category=UserWarning)
pd.set_option("display.max_colwidth", 100)

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
movies = pd.read_csv(find("movies.csv"), parse_dates=["release_date"])
awards = pd.read_csv(find("movie_awards.csv"))
crew = pd.read_csv(find("movie_crew.csv"))
cast = pd.read_csv(find("movie_cast.csv"))

movies = movies[movies["release_year"].notna()].copy()
movies["release_year"] = movies["release_year"].astype(int)
m = movies.set_index("film_id")
print(f"{len(m):,} films, {m['release_year'].min()}-{m['release_year'].max()}; "
      f"{len(awards):,} award rows, {len(crew):,} crew rows, {len(cast):,} cast rows")

# %% [markdown]
# # Part A. Best Picture
#
# ## A1. The label, and how complete it is
#
# A film is a **positive** if Wikidata records it as nominated for (or winning) the Academy Award
# for Best Picture. Films are grouped by release year: the ceremony is normally held early the
# following year (films released in 2025 competed at the March 2026 ceremony).
#
# Before modelling, check how many nominees per year the data actually records. The Academy
# nominated 5 films a year until the 2010 ceremony, between 8 and 10 until 2021, and exactly 10
# since the 2022 ceremony.

# %%
BP = "Academy Award for Best Picture"
bp_rows = awards[awards["award"] == BP]
m["bp_nom"] = m.index.isin(bp_rows["film_id"]).astype(int)
m["bp_win"] = m.index.isin(bp_rows.loc[bp_rows["outcome"] == "won", "film_id"]).astype(int)
LATEST = int(m.loc[m["bp_nom"] == 1, "release_year"].max())  # latest release year with nominees recorded
LAST_FULL = LATEST - 1  # the latest year is still being filled in on Wikidata, so keep it out of training

per_year = m[m["release_year"].between(1980, LATEST)].groupby("release_year")["bp_nom"].sum()
fig, ax = plt.subplots(figsize=(11, 3.8))
ax.bar(per_year.index, per_year.values, color=C[0], width=0.75)
ax.set_title("Best Picture nominees recorded per release year")
ax.set_ylabel("films")
gaps = per_year.loc[2009:][per_year.loc[2009:] < 8]
for year, n in gaps.items():
    ax.text(year, n + 0.25, str(n), ha="center", color=C[7], fontsize=9, fontweight="bold")
plt.show()
print("Years since 2009 with fewer than 8 nominees recorded:", gaps.to_dict())

# %% [markdown]
# Coverage is complete for most years, but some recent years are short. For those years some
# real nominees are counted as negatives. That makes the evaluation below **pessimistic**: a
# model that ranks a real-but-unrecorded nominee highly is scored as wrong.
#
# ## A2. Features known before the nominations
#
# The hard part of an awards model is **leakage**: using information that only exists *because*
# a film was nominated. The dataset has several such columns, and they are left out on purpose:
#
# - `oscar_nominations`, `oscar_wins` and the award rows themselves (they contain the answer);
# - `wikipedia_languages`: Oscar nominees get translated into many more languages *after* the
#   nomination, so it would make the model look far better than it can be on a new year;
# - `box_office_usd`: often recorded after the awards run, and boosted by it.
#
# What is left:
#
# | Group | Features |
# |---|---|
# | Genre | drama, biographical, historical, war, comedy, horror, science fiction, action, superhero, animated, documentary, musical, romance, crime |
# | Film | runtime, released September-December, English language, US production, sequel/series entry, based on another work |
# | Pedigree | Oscar nominations earned by the director's **earlier** films; the same for writers, producers, cinematographer, editor and composer |
# | Festivals | won a top festival prize (Cannes, Venice, Berlin, Toronto audience award); competed for the Palme d'Or, Golden Lion or Golden Bear |
# | Distribution | arthouse distributor (A24, Neon, Searchlight, Focus, Sony Pictures Classics, Mubi, ...), Netflix |
# | Critics | Metacritic and Rotten Tomatoes scores (missing values filled with the median) |
#
# The pedigree features only count films released in **earlier years**, so a director's
# nominations for this film (or for later films) never leak in.

# %%
genres = m["genres"].fillna("")
GENRES = {
    "drama": "drama film", "biographical": "biographical film", "historical": "historical film",
    "war": "war film", "comedy": "comedy film", "horror": "horror film", "science fiction": "science fiction film",
    "action": "action film", "superhero": "superhero film", "animated": "animated", "documentary": "documentary film",
    "musical": "musical film", "romance": "romance film", "crime": "crime film",
}
X = pd.DataFrame(index=m.index)
for name, label in GENRES.items():
    X[f"genre: {name}"] = genres.str.contains(label, regex=False).astype(int)

X["runtime (min)"] = m["runtime_min"].clip(60, 240).fillna(m["runtime_min"].median())
X["released Sep-Dec"] = (m["release_date"].dt.month >= 9).astype(int)
X["English language"] = m["original_languages"].fillna("").str.contains("English").astype(int)
X["US production"] = m["countries"].fillna("").str.contains("United States").astype(int)
X["sequel / series"] = m["series"].notna().astype(int)
X["based on a book etc."] = m["based_on"].notna().astype(int)
ARTHOUSE = "A24|Neon|Searchlight|Focus Features|Sony Pictures Classics|Mubi|Annapurna|Miramax"
X["arthouse distributor"] = m["distributors"].fillna("").str.contains(ARTHOUSE).astype(int)
X["Netflix"] = m["distributors"].fillna("").str.contains("Netflix").astype(int)

# Pedigree: Oscar nominations (any category) of each person's films from earlier years.
oscar = awards[awards["award"].str.startswith("Academy Award", na=False)][["film_id", "award"]].drop_duplicates()
oscars_per_film = oscar.groupby("film_id").size()


def prior_oscar_noms(people):
    """Per film: sum over its people of the Oscar nominations their films earned in earlier years."""
    p = people[["film_id", "person_id"]].drop_duplicates()
    p = p.assign(year=p["film_id"].map(m["release_year"]), noms=p["film_id"].map(oscars_per_film).fillna(0))
    p = p.dropna(subset=["year"])
    running = (p.groupby(["person_id", "year"])["noms"].sum().groupby(level=0).cumsum()
               .rename("career").reset_index().rename(columns={"year": "career_year"}))
    j = p.merge(running, on="person_id")
    j = j[j["career_year"] < j["year"]]  # strictly earlier years only
    per_person = j.sort_values("career_year").groupby(["film_id", "person_id"])["career"].last()
    return np.log1p(per_person.groupby(level=0).sum()).reindex(m.index).fillna(0)


X["director's past Oscar noms"] = prior_oscar_noms(crew[crew["role"] == "director"])
X["crew's past Oscar noms"] = prior_oscar_noms(
    crew[crew["role"].isin(["screenwriter", "producer", "cinematographer", "editor", "composer"])])

FESTIVAL_PRIZES = ["Palme d'Or", "Golden Lion", "Golden Bear", "Cannes Film Festival Grand Prix",
                   "Grand Jury Prize of the Venice Film Festival", "Silver Bear Grand Jury Prize",
                   "Toronto International Film Festival People's Choice Award"]
won = awards[awards["outcome"] == "won"]
X["won a festival prize"] = m.index.isin(won.loc[won["award"].isin(FESTIVAL_PRIZES), "film_id"]).astype(int)
X["in main festival competition"] = m.index.isin(
    awards.loc[awards["award"].isin(["Palme d'Or", "Golden Lion", "Golden Bear"]), "film_id"]).astype(int)
X["Metacritic"] = m["metacritic_score"].fillna(m["metacritic_score"].median())
X["Rotten Tomatoes"] = m["rotten_tomatoes_pct"].fillna(m["rotten_tomatoes_pct"].median())

FEATURES = list(X.columns)
X["year"], X["y"] = m["release_year"], m["bp_nom"]
X.loc[X["y"] == 1, FEATURES].mean().round(2).to_frame("mean among nominees").join(
    X.loc[X["y"] == 0, FEATURES].mean().round(2).rename("mean among others"))

# %% [markdown]
# ### Testing it the honest way: one year at a time
#
# For each release year from 2010 to 2024 the model is trained **only on earlier years** (from
# 1980), then ranks every film of that year. We count how many recorded nominees land in its top 10.
# This is how the model would have performed if it had been run in the autumn of each year.
#
# Two simpler baselines show whether the model adds anything:
# - **director pedigree**: rank films by the director's past Oscar nominations;
# - **critics only**: rank by Metacritic score.

# %%
START, FIRST_TEST = 1980, 2010


def nomination_model():
    return make_pipeline(StandardScaler(), LogisticRegression(C=0.3, class_weight="balanced", max_iter=3000))


rows = []
for year in range(FIRST_TEST, LAST_FULL + 1):
    train = X[(X["year"] >= START) & (X["year"] < year)]
    test = X[X["year"] == year].copy()
    test["p"] = nomination_model().fit(train[FEATURES], train["y"]).predict_proba(test[FEATURES])[:, 1]
    rows.append({
        "year": year, "recorded nominees": int(test["y"].sum()),
        "model": int(test.nlargest(10, "p")["y"].sum()),
        "director pedigree": int(test.nlargest(10, "director's past Oscar noms")["y"].sum()),
        "critics only": int(m.loc[test.index].nlargest(10, "metacritic_score").pipe(lambda t: t["bp_nom"].sum())),
    })
backtest = pd.DataFrame(rows).set_index("year")
totals = backtest.sum()
for col in ["model", "director pedigree", "critics only"]:
    print(f"{col:18s}: {totals[col]:3d} of {totals['recorded nominees']} nominees found in the top 10 "
          f"({totals[col] / totals['recorded nominees']:.0%})")
backtest.T

# %%
fig, ax = plt.subplots(figsize=(11, 4.2))
w = 0.27
ax.bar(backtest.index - w, backtest["recorded nominees"], w, color=MUTED, label="recorded nominees")
ax.bar(backtest.index, backtest["model"], w, color=C[0], label="found by the model (top 10)")
ax.bar(backtest.index + w, backtest["director pedigree"], w, color=C[1], label="found by director pedigree")
ax.set_title("Year-by-year test: nominees found in each method's top 10")
ax.set_xticks(backtest.index)
ax.set_ylabel("films")
ax.legend(loc="upper left", ncol=3)
ax.set_ylim(0, backtest["recorded nominees"].max() + 2.5)
plt.show()

# %% [markdown]
# The model finds close to 60% of the nominees in its top 10, clearly more than either
# baseline. That is a realistic level for an autumn forecast: the critics' awards, guild awards
# and the campaign season that shape the final list have not happened yet.
#
# ### What the model has learned
#
# Logistic regression coefficients on standardized features: a bar to the right means the
# feature raises the odds of a nomination, holding the others fixed.

# %%
final_nom_model = nomination_model().fit(X.loc[X["year"].between(START, LAST_FULL), FEATURES],
                                         X.loc[X["year"].between(START, LAST_FULL), "y"])
coef = pd.Series(final_nom_model[-1].coef_[0], FEATURES).sort_values()
fig, ax = plt.subplots(figsize=(11, 6.2))
ax.barh(coef.index, coef.values, color=[C[0] if v > 0 else C[1] for v in coef.values])
ax.axvline(0, color=INK2, lw=1)
ax.set_title("What raises (blue) or lowers (orange) the odds of a Best Picture nomination")
ax.set_xlabel("coefficient (per standard deviation)")
ax.grid(axis="y", visible=False)
plt.show()
print("Strongest positive:", ", ".join(coef.tail(4).index[::-1]))
print("Strongest negative:", ", ".join(coef.head(3).index))

# %% [markdown]
# ## A2b. Blind test: the 2026 ceremony
#
# Train only on films released up to 2024, then rank every 2025 film, the year whose winners were
# announced in March 2026. The model never saw these nominations.


# %%
def explain(model, rows, k=3):
    """Top k features pushing each film's score up (coefficient x standardized value)."""
    scaler, lr = model[0], model[-1]
    contrib = pd.DataFrame(scaler.transform(rows[FEATURES]) * lr.coef_[0], index=rows.index, columns=FEATURES)
    return contrib.apply(lambda r: ", ".join(r[r > 0].nlargest(k).index), axis=1)


def rank_year(year, train_until):
    train = X[(X["year"] >= START) & (X["year"] <= train_until)]
    model = nomination_model().fit(train[FEATURES], train["y"])
    test = X[X["year"] == year].copy()
    test["score"] = (100 * model.predict_proba(test[FEATURES])[:, 1]).round().astype(int)
    test = test.sort_values("score", ascending=False, kind="stable")
    test["rank"] = range(1, len(test) + 1)
    test["why"] = explain(model, test)
    return test.join(m[["title", "directors"]])


blind = rank_year(2025, train_until=2024)
# The nominees announced by the Academy on 22 January 2026 (98th Academy Awards). Wikidata does
# not record all of them yet, so the blind test is scored against this public list as well.
ANNOUNCED_2026 = ["Bugonia", "F1", "Frankenstein", "Hamnet", "Marty Supreme", "One Battle After Another",
                  "The Secret Agent", "Sentimental Value", "Sinners", "Train Dreams"]
blind["announced nominee"] = blind["title"].isin(ANNOUNCED_2026).astype(int)
print(f"{len(blind)} films released in 2025 are in the data; "
      f"{blind['announced nominee'].sum()} of the 10 announced nominees are among them.")
print(f"Announced nominees in the model's top 10: {blind.head(10)['announced nominee'].sum()}, "
      f"in its top 20: {blind.head(20)['announced nominee'].sum()}")
print(blind.loc[blind["announced nominee"] == 1, ["rank", "title", "score"]].to_string(index=False))
blind.head(15).set_index("rank")[["title", "directors", "score", "announced nominee", "why"]]

# %% [markdown]
# The **score** is the model's output scaled to 0-100. The model was trained with class
# balancing (nominees are only about 2-3% of films), so the score is a ranking, not a probability.
#
# Wikidata only records 3 of this ceremony's 10 nominees so far, but scored against the full
# announced list, 6 of the model's top 10 were real nominees, including the eventual winner at
# No. 1. The clear miss is *The Secret Agent*, a Portuguese-language Brazilian film. The model
# marks it down mostly for not being in English, then for having no US production and no crew
# with earlier Oscar nominations. Non-English nominees are rare in the training years, so the
# model has learned that bias from history; its Cannes prizes (best director and best actor) are
# not among the festival prizes used as features.
#
# ## A3. Forecast: films released in 2026
#
# Same model, now trained on every year up to 2025. These are the 2026 films most likely to be
# Best Picture nominees at the ceremony in early 2027, **based on what is known in the autumn**.

# %%
forecast_year = int(X["year"].max()) if (X["year"] == X["year"].max()).sum() > 100 else int(X["year"].max()) - 1
forecast = rank_year(forecast_year, train_until=forecast_year - 1)
print(f"{len(forecast)} films released in {forecast_year} are in the data so far.")
forecast.head(10).set_index("rank")[["title", "directors", "score", "why"]]

# %%
top = forecast.head(15).iloc[::-1]
fig, ax = plt.subplots(figsize=(11, 5.6))
ax.barh(top["title"], top["score"], color=[C[0] if r <= 10 else MUTED for r in top["rank"]])
for y, (score, why) in enumerate(zip(top["score"], top["why"])):
    ax.text(score + 1, y, f"{score}  {why}", va="center", fontsize=8.5, color=INK2)
ax.set_xlim(0, 150)
ax.set_xticks(range(0, 101, 20))
ax.set_title(f"Best Picture contenders among {forecast_year} releases (blue: predicted top 10)")
ax.set_xlabel("model score (a ranking, not a probability)")
ax.grid(axis="y", visible=False)
plt.show()

# %% [markdown]
# **How to read this list**
#
# - Read the score as a **ranking**, not as calibrated odds.
# - In the year-by-year test, a top 10 like this one contained a bit over half of the eventual
#   nominees. Expect several of these titles to miss and some films not on it (or not yet in the
#   data) to get in.
# - Many awards-season films premiere at festivals in September and open in cinemas in
#   November-December. Films enter the dataset once they have Wikipedia articles in 10 or more
#   languages, so late-year contenders appear in later weekly versions and the list will move.
#
# ## A4. Who wins?
#
# ### After the nominations: the "most nominations" rule
#
# Once nominations are announced, the strongest single signal is the oldest one: **the Best
# Picture nominee with the most Oscar nominations overall usually wins**. A logistic model with
# a few extra signals (Best Director, editing and screenplay nominations, BAFTA and Golden Globe
# wins, critic score), tested by leaving one ceremony out at a time, is compared with that rule.

# %%
def has_nom(pattern):
    return m.index.isin(oscar.loc[oscar["award"].str.contains(pattern, regex=True), "film_id"]).astype(int)


N = pd.DataFrame(index=m.index)
N["Oscar nominations"] = oscars_per_film.reindex(m.index).fillna(0)
N["Best Director nom"] = has_nom("Best Director")
N["Film Editing nom"] = has_nom("Film Editing")
N["screenplay nom"] = has_nom("Screenplay|Writing")
N["acting noms"] = oscar[oscar["award"].str.contains("Actor|Actress")].groupby("film_id").size().reindex(m.index).fillna(0)
N["BAFTA Best Film win"] = m.index.isin(won.loc[won["award"] == "BAFTA Award for Best Film", "film_id"]).astype(int)
N["Golden Globe win"] = m.index.isin(
    won.loc[won["award"].str.startswith("Golden Globe Award for Best Motion Picture"), "film_id"]).astype(int)
N["Metacritic"] = X["Metacritic"]
WIN_FEATURES = list(N.columns)
N["year"], N["win"] = m["release_year"], m["bp_win"]
nominees = N[m["bp_nom"] == 1]


def winner_model():
    return make_pipeline(StandardScaler(), LogisticRegression(C=0.5, max_iter=3000))


rule_hits = model_hits = ceremonies = 0
for year, field in nominees[nominees["year"].between(START, LAST_FULL)].groupby("year"):
    if field["win"].sum() != 1:  # skip years with a missing or duplicated winner record
        continue
    train = nominees[(nominees["year"] != year) & nominees["year"].between(START, LAST_FULL)]
    p = winner_model().fit(train[WIN_FEATURES], train["win"]).predict_proba(field[WIN_FEATURES])[:, 1]
    ceremonies += 1
    rule_hits += field["win"].iloc[field["Oscar nominations"].values.argmax()]
    model_hits += field["win"].iloc[p.argmax()]
print(f"Ceremonies for {START}-{LAST_FULL} films: {ceremonies}")
print(f"  most-nominations rule picked the winner: {rule_hits} times ({rule_hits / ceremonies:.0%})")
print(f"  logistic model picked the winner:        {model_hits} times ({model_hits / ceremonies:.0%})")
print(f"  picking a nominee at random:             ~{(1 / nominees.groupby('year').size().loc[START:LAST_FULL]).sum():.0f} times")

# %% [markdown]
# The extra signals do not beat the simple rule in this data (the precursor awards are only
# partly recorded on Wikidata), so the rule is the honest choice. It is right a bit over half the
# time, about three times better than picking a nominee at random. Upsets are common: the preferential ballot used
# for Best Picture rewards broadly liked films over divisive frontrunners.
#
# Applied to the 2026 ceremony:

# %%
last_ceremony = nominees[nominees["year"] == LATEST].join(m["title"])
last_ceremony = last_ceremony.sort_values("Oscar nominations", ascending=False)
pick = last_ceremony["title"].iloc[0]
print(f"Most-nominations pick among the recorded nominees: {pick}; recorded winner: "
      f"{', '.join(last_ceremony.loc[last_ceremony['win'] == 1, 'title']) or 'not recorded yet'}")
last_ceremony[["title", "Oscar nominations", "Best Director nom", "win"]]

# %% [markdown]
# ### Before the nominations: an early favourite, with honest odds
#
# For 2026 releases the nominations are not announced yet, so the rule above cannot run. The best
# the data offers now is the nomination ranking from A3. How often did that ranking contain the
# eventual winner in past years?

# %%
in_top10 = top1 = years = 0
for year in range(FIRST_TEST, LAST_FULL + 1):
    ranked = rank_year(year, train_until=year - 1)
    if m.loc[ranked.index, "bp_win"].sum() != 1:
        continue
    years += 1
    winners = m.loc[ranked.index, "bp_win"].values
    in_top10 += winners[:10].sum()
    top1 += winners[0]
print(f"{FIRST_TEST}-{LAST_FULL}: the winner was in the autumn top 10 in {in_top10} of {years} years, "
      f"and was the No. 1 pick in {top1} of {years}.")
nominated_now = nominees[nominees["year"] == forecast_year]
if len(nominated_now) >= 5:
    leader = nominated_now.join(m["title"]).sort_values("Oscar nominations", ascending=False)["title"].iloc[0]
    print(f"Nominations for {forecast_year} films are in the data: most-nominations pick = {leader}")
else:
    print(f"Early favourite for {forecast_year} films: {forecast['title'].iloc[0]} "
          f"(No. 1 in the nomination ranking). Re-run after the January nominations for a better call.")

# %% [markdown]
# So the early No. 1 is a weak bet on its own, but the autumn top 10 usually contains the winner.
# Once nominations for the 2026 films are added to Wikidata (late January 2027), the last cell
# switches to the most-nominations rule automatically on the next weekly data refresh.
#
# # Part B. Fan recommendations: "if you liked X, watch Y"
#
# A **content-based recommender**: two films are similar when they share the people and
# ingredients that fans notice: director, writers, composer, cinematographer, lead cast, genres,
# country, language, decade, and black-and-white or animation.
#
# Each film becomes a "bag of tags". The director counts three times, writers twice, genres twice,
# other crew and lead cast once. TF-IDF weights then make rare, specific tags (a particular
# composer) count for more than common ones (drama film), and cosine similarity finds the
# nearest films. A quality-and-popularity bonus (critic scores and how widely known a film is)
# favours well-reviewed films among similar candidates, which is what most people want from a
# recommendation.

# %%
def tag(prefix, value):
    return f"{prefix}:{str(value).strip().lower().replace(' ', '_')}"


bag = {fid: [] for fid in m.index}
for fid, gs in m["genres"].dropna().items():
    bag[fid] += [tag("genre", g) for g in gs.split("|")] * 2  # genres count double
weights = {"director": 3, "screenwriter": 2, "composer": 1, "cinematographer": 1, "editor": 1, "producer": 1}
for role, w in weights.items():
    for fid, pid in crew.loc[crew["role"] == role, ["film_id", "person_id"]].itertuples(index=False):
        if fid in bag:
            bag[fid] += [tag(role, pid)] * w
# Cast: keep the 8 most-credited actors per film (the cast list has no reliable billing order).
credits = cast["person_id"].map(cast["person_id"].value_counts())
lead_cast = cast.assign(credits=credits).sort_values("credits", ascending=False).groupby("film_id").head(8)
for fid, pid in lead_cast[["film_id", "person_id"]].itertuples(index=False):
    if fid in bag:
        bag[fid].append(tag("cast", pid))
for col, prefix in [("countries", "country"), ("original_languages", "lang")]:
    for fid, vals in m[col].dropna().items():
        bag[fid] += [tag(prefix, v) for v in vals.split("|")]
for fid, year in m["release_year"].items():
    bag[fid].append(f"decade:{year // 10 * 10}")
for fid in m.index[m["color_type"] == "black-and-white"]:
    bag[fid].append("look:black_and_white")

docs = [" ".join(bag[fid]) for fid in m.index]
vectorizer = TfidfVectorizer(token_pattern=r"[^ ]+", sublinear_tf=True, min_df=2)
V = normalize(vectorizer.fit_transform(docs))
ids = m.index.to_numpy()

critic = m[["rotten_tomatoes_pct", "metacritic_score"]].mean(axis=1).fillna(55) / 100
fame = np.log1p(m["wikipedia_languages"]) / np.log1p(m["wikipedia_languages"].max())
bonus = (0.5 * critic + 0.5 * fame).to_numpy()
names = {}
for kind in ["director", "screenwriter", "composer", "cinematographer", "editor", "producer"]:
    names.update(crew.loc[crew["role"] == kind].set_index("person_id")["person"].to_dict())
names.update(cast.set_index("person_id")["person"].to_dict())
print(f"{V.shape[0]:,} films x {V.shape[1]:,} tags")


def lookup(title):
    """Best match for a title: exact (case-insensitive) first, the most widely known version wins."""
    hits = m[m["title"].str.lower() == title.lower()]
    if hits.empty:
        hits = m[m["title"].str.contains(title, case=False, regex=False, na=False)]
    if hits.empty:
        raise KeyError(title)
    return hits["wikipedia_languages"].idxmax()


def readable(t):
    kind, value = t.split(":", 1)
    if kind in weights or kind == "cast":
        return f"{kind}: {names.get(value.upper(), value)}"
    return f"{kind}: {value.replace('_', ' ')}"


def recommend(*liked, n=8, quality_weight=0.3, per_director=None):
    """Films most similar to the liked titles, with the shared tags that explain each pick.

    per_director caps how many films by the same director are suggested, for more variety.
    """
    liked_ids = [lookup(t) for t in liked]
    rows = [np.flatnonzero(ids == fid)[0] for fid in liked_ids]
    profile = normalize(np.asarray(V[rows].mean(axis=0)))
    sim = (V @ profile.T).ravel()
    score = (1 - quality_weight) * sim + quality_weight * bonus * (sim > 0)
    score[rows] = -1
    vocab = np.array(vectorizer.get_feature_names_out())
    out, seen = [], {}
    for i in np.argsort(-score):
        if len(out) == n:
            break
        director = m["directors"].iloc[i]
        if per_director and isinstance(director, str):
            if seen.get(director, 0) >= per_director:
                continue
            seen[director] = seen.get(director, 0) + 1
        shared = V[i].multiply(profile).toarray().ravel()  # each tag's contribution to the similarity
        best = vocab[np.argsort(-shared)[:3]][np.sort(shared)[::-1][:3] > 0]
        out.append({"title": m["title"].iloc[i], "year": m["release_year"].iloc[i],
                    "directors": m["directors"].iloc[i], "similarity": round(float(sim[i]), 2),
                    "because": "; ".join(readable(t) for t in best)})
    return pd.DataFrame(out)


recommend("Inception")

# %%
recommend("Spirited Away")

# %% [markdown]
# Liking *Inception* or *Spirited Away* mostly means liking their directors, so the top picks are
# their other films. Fans who have seen those can cap the number of films per director to explore
# further:

# %%
recommend("The Godfather", per_director=1)

# %% [markdown]
# ### Several favourites at once
#
# Pass more than one title and the recommender averages their profiles, which is how a fan's
# taste usually looks: here, someone who liked a Korean thriller and an American satire.

# %%
recommend("Parasite", "Get Out")

# %% [markdown]
# ### Does it work? A quick sanity check
#
# Film series were **not** given to the recommender as a tag, which makes them a fair test:
# for a film in a series, does another entry of the same series appear in its top 10? Sequels
# share cast, crew and genre, so a sensible recommender should find them often, but not always.

# %%
in_series = m[m["series"].notna()]
series_size = in_series["series"].value_counts()
sample = in_series[in_series["series"].map(series_size) >= 2].sample(400, random_state=0)
found = 0
for fid, series in sample["series"].items():
    row = np.flatnonzero(ids == fid)[0]
    sim = (V @ V[row].T).toarray().ravel()
    sim[row] = -1
    found += (m["series"].iloc[np.argsort(-sim)[:10]] == series).any()
print(f"Another film from the same series was in the top 10 for {found} of {len(sample)} films "
      f"({found / len(sample):.0%}).")

# %% [markdown]
# ## Takeaways
#
# - **Best Picture nominations are fairly predictable in the autumn.** Critic scores, English
#   language, the crew's Oscar track record, drama and longer runtimes push a film up;
#   documentaries, action films and sequels push it down. The top 10 holds close to 60% of the
#   nominees, well ahead of simple baselines, and 6 of the 10 nominees in the blind 2026 test.
# - **The model inherits the Academy's history.** It underrates non-English films such as
#   *The Secret Agent*, because they were rarely nominated in the years it learned from.
# - **The winner is much harder.** After nominations, "most nominations wins" is right a bit over
#   half the time. Before nominations, the eventual winner is usually somewhere in the top 10 but
#   rarely the No. 1 pick.
# - **Leakage matters.** Columns that are filled in *because* of the Oscars (nomination counts,
#   Wikipedia translations, box office) would make the model look much better than it really is.
# - **Content-based recommendations are explainable.** Every suggestion comes with the shared
#   director, composer or genre that produced it, and the method needs no user ratings.
#
# Ideas to take further: add the critics' and guild awards as they are announced, try gradient
# boosting, or blend this recommender with ratings data for a hybrid system.
