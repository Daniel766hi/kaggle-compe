# %% [markdown]
# # IMDb in SQLite: build and query in minutes
#
# Building takes about 25 minutes (all core tables, 17 GB); after that, queries take seconds.
#
# This notebook uses the **[IMDb SQLite Builder](https://www.kaggle.com/datasets/danielaijdkx/imdb-sqlite-database)**
# to download IMDb's official datasets (https://datasets.imdbws.com) and load them into one SQLite
# database, then runs a few SQL queries. IMDb's data is for personal and non-commercial use; it is
# downloaded here, directly from IMDb, rather than stored on Kaggle.
#
# **Settings:** this notebook needs *Internet on* (it is enabled in this notebook's settings).

# %%
import glob
import os
import shutil
import sqlite3
import subprocess
import sys
import time

import pandas as pd

pd.set_option("display.max_colwidth", 60)
builder = glob.glob("/kaggle/input/**/build_imdb_sqlite.py", recursive=True)[0]
work = "/tmp"  # the database is about 17 GB; /tmp has far more room than /kaggle/working
db = os.path.join(work, "imdb.sqlite")
free_gb = shutil.disk_usage(work).free / 1e9
print(f"Builder: {builder}\nDatabase: {db}\nFree disk: {free_gb:.0f} GB")

# %%
start = time.time()
subprocess.run([sys.executable, builder, "--db", db], check=True)
print(f"Built in {(time.time() - start) / 60:.1f} minutes; file size {os.path.getsize(db) / 1e9:.1f} GB")

# %%
con = sqlite3.connect(db)
tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table' "
                                    "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
counts_df = pd.DataFrame({"rows": counts}).sort_values("rows", ascending=False)
print(counts_df.to_string(formatters={"rows": "{:,}".format}))
print("COUNTS_JSON", {**counts, "built_on": time.strftime("%Y-%m-%d")})

# %% [markdown]
# ## The best-rated movies (IMDb-style weighted rating)

# %%
top = pd.read_sql("SELECT primary_title, start_year, average_rating, num_votes, weighted_rating "
                  "FROM top_rated_movies LIMIT 15", con)
print(top.head(5).to_string(index=False))
top

# %% [markdown]
# ## Which genres rate best, decade by decade?

# %%
summary = pd.read_sql("SELECT * FROM genre_decade_summary WHERE decade >= 1960 AND movies >= 200", con)
summary.pivot(index="genre", columns="decade", values="avg_rating").round(2).sort_values(2020, ascending=False).head(12)

# %% [markdown]
# ## Directors with the most well-rated movies

# %%
pd.read_sql("""
SELECT n.primary_name AS director, COUNT(*) AS movies, ROUND(AVG(r.average_rating), 2) AS avg_rating,
       SUM(r.num_votes) AS votes
FROM title_principals p
JOIN title_basics b ON b.tconst = p.tconst AND b.title_type = 'movie'
JOIN title_ratings r ON r.tconst = p.tconst AND r.num_votes >= 50000
JOIN name_basics n ON n.nconst = p.nconst
WHERE p.category = 'director'
GROUP BY p.nconst HAVING COUNT(*) >= 8
ORDER BY avg_rating DESC LIMIT 15
""", con)

# %% [markdown]
# ## Longest-running TV series by number of episodes

# %%
pd.read_sql("""
SELECT b.primary_title, b.start_year, b.end_year, COUNT(*) AS episodes, MAX(e.season_number) AS seasons
FROM title_episode e JOIN title_basics b ON b.tconst = e.parent_tconst
GROUP BY e.parent_tconst ORDER BY episodes DESC LIMIT 10
""", con)

# %% [markdown]
# ## Your turn
#
# The database is now at the path printed above. Try joining `title_principals` with `name_basics` to
# follow an actor's career, or `title_genres` with `title_ratings` to compare genres. Add `--all`
# to the build command to also load `title_akas` (alternative and international titles).
#
# Data courtesy of IMDb (https://www.imdb.com), used under IMDb's non-commercial terms.
