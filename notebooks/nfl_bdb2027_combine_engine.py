# %% [markdown]
# # How many NFL games is the Combine worth?
#
# Companion notebook for the NFL Big Data Bowl 2027 writeup. Every number and figure in the writeup is
# produced here from the competition data.
#
# **Idea.** A sprint is described by two numbers: the top speed an athlete is heading towards (**S0**)
# and how hard he can accelerate from a standstill (**A0**). Both can be measured from the 10 Hz
# tracking of the Combine 40-yard dash (mono-exponential sprint model, Samozino et al. 2016) *and*
# from the same rookie's NFL game tracking (in-situ acceleration-speed profile, Morin et al. 2021),
# in the same units. That lets us ask directly how much of the Combine engine shows up on Sundays,
# and how many NFL games of tracking the Combine is worth.
#
# Sections
# 1. The 40-yard dash, decomposed
# 2. The game engine: in-game acceleration-speed profiles
# 3. What carries over from Combine to games
# 4. How many games is the Combine worth?
# 5. Does the game engine matter for play outcomes?
# 6. The Rookie Engine Card (weekly use)

# %%
import glob
import os
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm

warnings.filterwarnings("ignore")
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 40)

# INLINE: nfl_bdb2027
from nfl_bdb2027.build_features import combine_tables, game_tables  # noqa: E402
from nfl_bdb2027.movement import BIN, fit_as_profile, robust_envelope, split_half, spearman_brown  # noqa: E402

INK, INK2, GRID, SURFACE, MUTED = "#0b0b0b", "#52514e", "#e6e5e0", "#fcfcfb", "#c3c2b7"
COL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
POS_ORDER = ["WR", "DB", "TE", "DL", "OL"]
POS_COLOR = dict(zip(POS_ORDER, COL))
plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
    "axes.titlesize": 12.5, "axes.titleweight": "bold", "axes.titlecolor": INK, "axes.titlelocation": "left",
    "font.size": 10.5, "lines.linewidth": 2, "figure.figsize": (11, 4.6), "figure.dpi": 110,
    "legend.frameon": False,
})
FIG_DIR = os.environ.get("FIG_DIR")
MPH = 3600 / 1760  # yd/s -> mph


def save(fig, name):
    if FIG_DIR:
        os.makedirs(FIG_DIR, exist_ok=True)
        fig.savefig(f"{FIG_DIR}/{name}.png", dpi=150, bbox_inches="tight")
    plt.show()


def find(name):
    """Locate a competition file on Kaggle (/kaggle/input) or locally (DATA_ROOT)."""
    for root in ("/kaggle/input", os.environ.get("DATA_ROOT", "../input")):
        hits = glob.glob(f"{root}/**/{name}", recursive=True)
        if hits:
            return hits[0]
    raise FileNotFoundError(name)


def boot_ci(x, y, n=2000, seed=0, method="pearson"):
    """Correlation with a player-level bootstrap 95% interval."""
    d = pd.DataFrame({"x": x, "y": y}).dropna()
    rng = np.random.default_rng(seed)
    r = d.corr(method=method).iloc[0, 1]
    idx = rng.integers(0, len(d), (n, len(d)))
    xs, ys = d.x.to_numpy()[idx], d.y.to_numpy()[idx]
    if method == "spearman":
        xs, ys = xs.argsort(1).argsort(1), ys.argsort(1).argsort(1)
    xs = xs - xs.mean(1, keepdims=True)
    ys = ys - ys.mean(1, keepdims=True)
    bs = (xs * ys).sum(1) / np.sqrt((xs ** 2).sum(1) * (ys ** 2).sum(1))
    lo, hi = np.nanpercentile(bs, [2.5, 97.5])
    return r, lo, hi, len(d)


def resid(df, y, ctrl):
    X = pd.get_dummies(df[ctrl], drop_first=True, dtype=float) if ctrl else None
    if X is None or X.shape[1] == 0:
        return df[y] - df[y].mean()
    return sm.OLS(df[y].astype(float), sm.add_constant(X)).fit().resid


# %% [markdown]
# ## 0. Data
# Raw tracking is reduced once to compact tables: for every player x game (and every Combine drill
# attempt) and every 0.25 yd/s speed bin, the best acceleration and the hardest braking produced.
# Acceleration is the change in (lightly smoothed) speed per second, because the provided `a` column
# is a magnitude and cannot tell braking from speeding up.

# %%
DATA = os.path.dirname(find("players.csv"))
CACHE = os.environ.get("FEATURE_DIR", "/kaggle/working/features")
os.makedirs(CACHE, exist_ok=True)
if not os.path.exists(f"{CACHE}/game_bins.parquet"):
    cb, sprints = combine_tables(f"{DATA}/combine_tracking.csv")
    cb.to_parquet(f"{CACHE}/combine_bins.parquet")
    sprints.to_parquet(f"{CACHE}/combine_sprints.parquet")
    bins, speed = zip(*[game_tables(f) for f in sorted(glob.glob(f"{DATA}/game_tracking_*.csv"))])
    pd.concat(bins).to_parquet(f"{CACHE}/game_bins.parquet")
    pd.concat(speed).to_parquet(f"{CACHE}/game_speed.parquet")

cbins = pd.read_parquet(f"{CACHE}/combine_bins.parquet")
sprints = pd.read_parquet(f"{CACHE}/combine_sprints.parquet")
gbins = pd.read_parquet(f"{CACHE}/game_bins.parquet").reset_index(drop=True)
gspeed = pd.read_parquet(f"{CACHE}/game_speed.parquet")
players = pd.read_csv(f"{DATA}/players.csv").set_index("nfl_id")
combine = pd.read_csv(f"{DATA}/combine_results.csv").set_index("nfl_id")
games = pd.read_csv(f"{DATA}/games.csv")

# chronological game index per player
order = gbins[["nfl_id", "game_id"]].drop_duplicates().sort_values(["nfl_id", "game_id"])
order["gi"] = order.groupby("nfl_id").cumcount() + 1
gbins = gbins.merge(order, on=["nfl_id", "game_id"])
n_games = order.groupby("nfl_id").gi.max().rename("games")
print(f"{combine.shape[0]} prospects, {sprints.nfl_id.nunique()} with a tracked 40, "
      f"{n_games.size} with NFL game tracking, {len(order)} player-games")

# %% [markdown]
# ## 1. The 40-yard dash, decomposed
# Fit `v(t) = S0 (1 - exp(-(t - t0)/tau))` to each tracked 40 (best attempt by peak speed).
# Acceleration then falls on a straight line from **A0 = S0/tau** at zero speed to zero at **S0**.

# %%
sp = sprints[(sprints.rmse < 0.4) & (sprints.S0 < 13.5)]
c40 = sp.sort_values("peak_speed", ascending=False).groupby("nfl_id").first()
c40 = c40[["S0", "A0", "tau", "peak_speed", "rmse"]].add_suffix("_c")
P = combine[["combine_position", "combine_weight", "forty", "ten_yd_split", "vertical", "broad_jump",
             "three_cone", "short_shuttle", "ngs_athleticism_score"]].join(c40)
P = P.join(players[["display_name", "draft_overall_pick", "draft_year"]]).join(n_games)
P["log_pick"] = np.log(P.draft_overall_pick.fillna(300))
print(f"usable 40 fits: {c40.shape[0]} players; median fit RMSE {c40.rmse_c.median():.2f} yd/s")
print(P[["forty", "ten_yd_split", "S0_c", "A0_c", "tau_c", "peak_speed_c"]].corr().round(2))

# %%
# How much of the official 40 and 10-yd split is explained by each tracked parameter (within position)?
rows = []
for y in ["forty", "ten_yd_split"]:
    for x in ["S0_c", "tau_c", "A0_c"]:
        d = P[[y, x, "combine_position"]].dropna()
        r = np.corrcoef(resid(d, y, ["combine_position"]), resid(d, x, ["combine_position"]))[0, 1]
        rows.append({"official time": y, "tracking parameter": x, "within-position r": round(r, 2), "n": len(d)})
decomp = pd.DataFrame(rows)
print(decomp.to_string(index=False))

# %%
fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
d = P.dropna(subset=["S0_c", "tau_c", "forty"])
for pos in POS_ORDER:
    q = d[d.combine_position == pos]
    axes[0].scatter(q.S0_c * MPH, q.forty, s=14, alpha=0.7, color=POS_COLOR[pos], label=pos)
    axes[1].scatter(q.tau_c, q.forty, s=14, alpha=0.7, color=POS_COLOR[pos])
axes[0].set(xlabel="Top-speed capacity S0 from tracking (mph)", ylabel="Official 40 time (s)",
            title="The 40 time is a top-speed test...")
axes[1].set(xlabel="Acceleration time constant tau (s; lower = quicker)",
            title="...and is blind to how quickly a player gets there")
axes[0].legend(ncol=5, loc="upper right", fontsize=9)
for ax, x in zip(axes, ["S0_c", "tau_c"]):
    r = decomp.query("`official time` == 'forty' and `tracking parameter` == @x")["within-position r"].item()
    ax.text(0.02, 0.04, f"within-position r = {r:+.2f}", transform=ax.transAxes, color=INK,
            bbox=dict(facecolor=SURFACE, edgecolor=GRID, boxstyle="round,pad=0.3"))
fig.tight_layout()
save(fig, "fig1_forty_decomposed")

# %% [markdown]
# ## 2. The game engine
# For each rookie, pool all game frames, take in every speed bin the **second-best** acceleration seen
# across games (one glitchy frame cannot set the profile), and fit the straight line of the in-situ
# acceleration-speed profile from the speed of peak acceleration upward (Morin et al. 2021).

# %%
def as_profiles(bins, k=2):
    env = robust_envelope(bins, ["nfl_id"], k=k)
    return pd.DataFrame({p: fit_as_profile(e.bin, e.acc_max) for p, e in env.groupby("nfl_id")}).T.astype(float)


def brake_capacity(bins, k=2, lo=3.0, hi=7.0):
    """Hardest sustained-sample braking between lo and hi yd/s (mean over bins of the k-th hardest)."""
    env = robust_envelope(bins, ["nfl_id"], col="acc_min", k=k, highest=False)
    v = (env.bin + 0.5) * BIN
    e = env[(v >= lo) & (v < hi)]
    full = e.groupby("nfl_id").bin.size() == int((hi - lo) / BIN)
    return -e.groupby("nfl_id").acc_min.mean()[full]


G = as_profiles(gbins)
G["B"] = brake_capacity(gbins)
G = G.add_suffix("_g")
P = P.join(G)
print(G.describe().round(2))

# split-half reliability across games (players with >= 8 games)
many = P.index[P.games >= 8]


def half_profile(d):
    e = robust_envelope(d, ["nfl_id"], k=2)
    out = fit_as_profile(e.bin, e.acc_max)
    out["B"] = brake_capacity(d).mean() if len(d) else np.nan
    return out


sh = split_half(gbins[gbins.nfl_id.isin(many)], "nfl_id", "game_id", half_profile)
rel = {}
for c in ["S0", "A0", "B"]:
    a, b = sh.half_a.map(lambda x: x[c]), sh.half_b.map(lambda x: x[c])
    ok = a.notna() & b.notna()
    r = np.corrcoef(a[ok], b[ok])[0, 1]
    rel[c] = {"split-half r": round(r, 2), "reliability (Spearman-Brown)": round(spearman_brown(r), 2), "n": int(ok.sum())}
rel = pd.DataFrame(rel).T
print(rel)

# %% [markdown]
# ## 3. What carries over from the Combine to games
# Same units, same model: compare the Combine 40 profile (S0_c, A0_c) with the in-game profile
# (S0_g, A0_g) for rookies with at least 8 games. Braking capacity in games is compared with the
# hardest braking a player showed in the Combine agility and position drills.

# %%
fam = cbins.drill_type.map({"FORTY_YARD_DASH": "forty"}).fillna("drills")
P["B_c"] = brake_capacity(cbins[fam == "drills"].rename(columns={"event_id": "unit"}), k=1)

carry = []
d8 = P[P.games >= 8]
for pos in POS_ORDER:
    q = d8[d8.combine_position == pos]
    for trait, (x, y) in {"Top speed S0": ("S0_c", "S0_g"), "Acceleration A0": ("A0_c", "A0_g"),
                          "Braking": ("B_c", "B_g")}.items():
        r, lo, hi, n = boot_ci(q[x], q[y])
        carry.append({"position": pos, "trait": trait, "r": r, "lo": lo, "hi": hi, "n": n})
carry = pd.DataFrame(carry)
print(carry.round(2).to_string(index=False))

P["speed_used"] = P.S0_g / P.S0_c
P["accel_used"] = P.A0_g / P.A0_c
print(d8.assign(speed_used=P.speed_used, accel_used=P.accel_used)
      .groupby("combine_position")[["S0_c", "S0_g", "speed_used", "A0_c", "A0_g", "accel_used"]].median().round(2))

# %%
fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.6), gridspec_kw={"width_ratios": [1.25, 1]})
ax = axes[0]
traits = ["Top speed S0", "Acceleration A0", "Braking"]
for i, t in enumerate(traits):
    q = carry[carry.trait == t].set_index("position").loc[POS_ORDER]
    y = np.arange(len(POS_ORDER)) + (i - 1) * 0.25
    ax.errorbar(q.r, y, xerr=[q.r - q.lo, q.hi - q.r], fmt="o", color=COL[i], label=t, capsize=0, lw=1.5)
ax.axvline(0, color=INK2, lw=1)
ax.set_yticks(range(len(POS_ORDER)), POS_ORDER)
ax.invert_yaxis()
ax.set(xlabel="Correlation, Combine value vs. same trait in NFL games (95% bootstrap CI)",
       title="Top speed carries over; acceleration and braking barely do")
ax.legend(loc="lower right", fontsize=9)
ax = axes[1]
for i, pos in enumerate(POS_ORDER):
    v = d8.loc[d8.combine_position == pos].index
    vals = P.loc[v, "speed_used"].dropna() * 100
    ax.boxplot(vals, positions=[i], widths=0.55, vert=True, patch_artist=True, showfliers=False,
               boxprops=dict(facecolor=POS_COLOR[pos], alpha=0.35, color=POS_COLOR[pos]),
               medianprops=dict(color=INK), whiskerprops=dict(color=INK2), capprops=dict(color=INK2))
ax.axhline(100, color=INK2, lw=1, ls="--")
ax.set_xticks(range(len(POS_ORDER)), POS_ORDER)
ax.set(ylabel="In-game S0 as % of Combine S0", title="Share of Combine top speed used in games")
fig.tight_layout()
save(fig, "fig2_carry_over")

# %%
# Robustness: carry-over within position after removing body weight (heavier players are slower and
# brake less in both settings, which alone can create a Combine-game correlation).
rob = []
for pos in POS_ORDER:
    q = d8[d8.combine_position == pos]
    for trait, (x, y) in {"Top speed S0": ("S0_c", "S0_g"), "Acceleration A0": ("A0_c", "A0_g"),
                          "Braking": ("B_c", "B_g")}.items():
        z = q[[x, y, "combine_weight"]].dropna()
        r = np.corrcoef(resid(z, x, ["combine_weight"]), resid(z, y, ["combine_weight"]))[0, 1]
        rob.append({"position": pos, "trait": trait, "r | weight": round(r, 2), "n": len(z)})
print(pd.DataFrame(rob).pivot(index="position", columns="trait", values="r | weight").loc[POS_ORDER])

# %% [markdown]
# Attempt-to-attempt reliability of the 40 fit (players with two usable attempts). It caps how
# strongly any Combine parameter can correlate with anything else.

# %%
two = sp.sort_values("attempt").groupby("nfl_id").filter(lambda d: len(d) >= 2).groupby("nfl_id").head(2)
two = two.assign(k=two.groupby("nfl_id").cumcount()).pivot(index="nfl_id", columns="k", values=["S0", "tau", "A0"])
retest = pd.Series({c: two[c].corr().iloc[0, 1] for c in ["S0", "tau", "A0"]}).round(2)
print(f"test-retest r across two 40 attempts (n={len(two)}):", retest.to_dict())

# %% [markdown]
# ## 4. How many NFL games is the Combine worth?
# For rookies with at least 16 games, the **target** is the engine they show in games 9 onward.
# Everything is compared *within position and body weight*: we remove position-group means and
# weight from target and predictors, so a WR is never credited for being faster than a guard.
#
# Predictors: the Combine (official 40 time; tracked S0_c, A0_c; drill braking) versus the same
# profile measured from only the first *k* NFL games. The share of individual variance each explains
# (squared partial correlation) tells us how many games of NFL tracking the Combine is worth.

# %%
TRAITS = {"S0": "Top speed S0", "A0": "Acceleration A0", "B": "Braking"}
K = [1, 2, 3, 4, 6, 8]
ids = P.index[(P.games >= 16) & P.S0_c.notna() & P.forty.notna()]
gk = gbins[gbins.nfl_id.isin(ids)]
target = as_profiles(gk[gk.gi > 8])
target["B"] = brake_capacity(gk[gk.gi > 8])
early = {}
for k in K:
    e = gk[gk.gi <= k]
    early[k] = as_profiles(e, k=min(2, k))  # same definition as the target (second best once >= 2 games)
    early[k]["B"] = brake_capacity(e, k=min(2, k))

ctrl = P.loc[ids, ["combine_position", "combine_weight"]]
cols = {"T_" + t: target[t] for t in TRAITS}
cols.update({"forty": -P.loc[ids, "forty"], "S0_c": P.loc[ids, "S0_c"], "A0_c": P.loc[ids, "A0_c"],
             "B_c": P.loc[ids, "B_c"]})
cols.update({f"{t}_{k}": early[k][t] for t in TRAITS for k in K})
R = pd.DataFrame(cols).reindex(ids)
# residualise every column on position + weight (players with a missing value drop out per column)
for c in R:
    d = ctrl.join(R[c].rename("v")).dropna()
    R.loc[d.index, c] = resid(d, "v", ["combine_position", "combine_weight"])

COMBINE = {"S0": ["S0_c", "forty"], "A0": ["A0_c"], "B": ["B_c"]}


def share(df, x, y):
    d = df[[x, y]].dropna()
    return np.corrcoef(d[x], d[y])[0, 1] ** 2 if len(d) > 20 else np.nan


def equivalent(curve, c):
    """Games at which the game-only curve reaches the Combine's share (linear interpolation)."""
    ks = np.array([0] + K, dtype=float)
    g = np.r_[0.0, curve]
    if c <= 0:
        return 0.0
    above = np.flatnonzero(g >= c)
    if len(above) == 0:
        return np.nan  # beyond 8 games
    j = above[0]
    return ks[j - 1] + (c - g[j - 1]) / (g[j] - g[j - 1]) * (ks[j] - ks[j - 1])


def worth(df):
    out = {}
    for t, cs in COMBINE.items():
        curve = [share(df, f"{t}_{k}", "T_" + t) for k in K]
        for c in cs:
            out[(t, c)] = (share(df, c, "T_" + t), equivalent(curve, share(df, c, "T_" + t)), curve)
    return out


point = worth(R)
rng = np.random.default_rng(1)
boot = [worth(R.iloc[rng.integers(0, len(R), len(R))]) for _ in range(500)]
rows = []
for key, (sh_c, eq, curve) in point.items():
    eqs = np.array([b[key][1] for b in boot])
    lo, hi = np.nanpercentile(np.where(np.isnan(eqs), 99, eqs), [5, 95])  # NaN = more than 8 games
    rows.append({"trait": TRAITS[key[0]], "Combine measure": key[1], "share explained by Combine": sh_c,
                 "share explained by game 1": curve[0], "by 4 games": curve[3], "by 8 games": curve[-1],
                 "games the Combine is worth": eq, "90% interval": f"{lo:.1f} to {'>8' if hi > 8 else f'{hi:.1f}'}"})
worth_table = pd.DataFrame(rows)
print(f"n = {len(ids)} rookies with 16+ games")
print(worth_table.round(3).to_string(index=False))

# %%
fig, axes = plt.subplots(1, 3, figsize=(12, 4.2), sharey=True)
for ax, (t, label) in zip(axes, TRAITS.items()):
    curve = point[(t, COMBINE[t][0])][2]
    bs = np.array([b[(t, COMBINE[t][0])][2] for b in boot])
    lo, hi = np.nanpercentile(bs, [5, 95], axis=0)
    ax.fill_between(K, lo * 100, hi * 100, color=COL[0], alpha=0.15, lw=0)
    ax.plot(K, np.array(curve) * 100, "o-", color=COL[0], label="first k NFL games")
    for c, col, ls in zip(COMBINE[t], [COL[1], COL[3]], ["-", "--"]):
        v = point[(t, c)][0] * 100
        ax.axhline(v, color=col, ls=ls, lw=2, label={"S0_c": "Combine tracking (S0)", "forty": "Combine 40 time",
                                                     "A0_c": "Combine tracking (A0)", "B_c": "Combine drill braking"}[c])
        eq = point[(t, c)][1]
        if c == COMBINE[t][0]:
            txt = "worth > 8 games" if np.isnan(eq) else f"Combine worth {eq:.1f} games"
            ax.text(0.02, 0.98, txt, transform=ax.transAxes, ha="left", va="top", color=col, fontweight="bold")
    ax.set(title=label, xlabel="NFL games observed", xticks=K, ylim=(-1, 40))
    ax.legend(loc="upper left", fontsize=8.5, bbox_to_anchor=(0, 0.88))
axes[0].set_ylabel("% of individual variance in games 9+ explained")
fig.suptitle("How many NFL games of tracking is the Combine worth? (within position and weight)",
             x=0.01, ha="left", fontweight="bold", color=INK)
fig.tight_layout()
save(fig, "fig3_games_worth")

# %% [markdown]
# ## 5. Does the engine matter on Sundays?
# Per-snap NGS outcomes, by role, for players with enough snaps:
# - **Pass rushers** (all players with a recorded get-off): average get-off (s, lower is better) and
#   pressure rate (pressures / rush snaps, beta-binomial shrinkage).
# - **Receivers** (WR, TE): separation at pass release on every route run, minus the average for that
#   route type (route-adjusted separation).
# - **Offensive linemen**: pressure-allowed rate per pass-block snap (shrunk).
#
# Each correlation is *partial*: it removes body weight, draft slot (log overall pick; undrafted = 300)
# and role (share of snaps lined up on the edge, in the slot, or at tackle). Intervals are player
# bootstrap 95%; q-values control the false discovery rate across all tests (Benjamini-Hochberg).

# %%
from statsmodels.stats.multitest import multipletests  # noqa: E402

from nfl_bdb2027.movement import eb_shrink  # noqa: E402

pp_cols = ["game_id", "play_id", "nfl_id", "lined_up_position", "route_ran", "separation_at_pass_forward",
           "pressure_allowed", "player_get_off", "time_to_pressure", "play_nullified_by_penalty"]
pp = pd.read_csv(find("player_play.csv"), usecols=pp_cols)
pp = pp[pp.play_nullified_by_penalty != "Y"]

r = pp[pp.separation_at_pass_forward.notna() & pp.route_ran.notna()].copy()
r["sep_adj"] = r.separation_at_pass_forward - r.groupby("route_ran").separation_at_pass_forward.transform("mean")
rec = r.groupby("nfl_id").agg(routes=("sep_adj", "size"), sep_adj=("sep_adj", "mean"),
                              slot_share=("lined_up_position", lambda x: x.isin(["SLOT_WR", "TE"]).mean()))
o = pp[pp.pressure_allowed.notna()]
ol = o.groupby("nfl_id").agg(pass_blocks=("pressure_allowed", "size"), pressures_allowed=("pressure_allowed", "sum"),
                             tackle_share=("lined_up_position", lambda x: (x == "T").mean()))
d = pp[pp.player_get_off.notna()]
rush = d.groupby("nfl_id").agg(rushes=("player_get_off", "size"), get_off=("player_get_off", "mean"),
                               pressures=("time_to_pressure", lambda x: x.notna().sum()),
                               edge_share=("lined_up_position", lambda x: (x == "EDGE").mean()))
O = P.join(rec).join(ol).join(rush)
m = O.pass_blocks >= 100
O.loc[m, "pressure_allowed_rate"] = eb_shrink(O.pressures_allowed[m].astype(float), O.pass_blocks[m])
m = O.rushes >= 100
O.loc[m, "pressure_rate"] = eb_shrink(O.pressures[m].astype(float), O.rushes[m])

OUTCOMES = {
    "Pass rush: get-off (faster)": (O.rushes >= 100, "get_off", -1, ["edge_share"]),
    "Pass rush: pressure rate": (O.rushes >= 100, "pressure_rate", 1, ["edge_share"]),
    "Receiver: route-adj. separation": (O.routes >= 100, "sep_adj", 1, ["slot_share"]),
    "OL: pressure allowed (fewer)": (O.pass_blocks >= 100, "pressure_allowed_rate", -1, ["tackle_share"]),
}
PRED = {"Game A0": "A0_g", "Game S0": "S0_g", "Game braking": "B_g",
        "Combine A0": "A0_c", "Combine S0": "S0_c", "40 time (faster)": "forty"}
rows = []
for oname, (mask, y, sign, role) in OUTCOMES.items():
    for pname, x in PRED.items():
        q = O[mask].copy()
        q["y"] = sign * q[y]
        q["x"] = -q[x] if x == "forty" else q[x]
        c = ["combine_weight", "log_pick"] + role
        q = q[["x", "y"] + c].dropna()
        rr, lo, hi, n = boot_ci(resid(q, "x", c), resid(q, "y", c))
        t = rr * np.sqrt((n - 2 - len(c)) / (1 - rr ** 2))
        from scipy import stats
        pval = 2 * stats.t.sf(abs(t), n - 2 - len(c))
        rows.append({"outcome": oname, "predictor": pname, "r": rr, "lo": lo, "hi": hi, "n": n, "p": pval})
link = pd.DataFrame(rows)
link["q"] = multipletests(link.p, method="fdr_bh")[1]
print(link.round(3).to_string(index=False))

# %% [markdown]
# **Reading.** After removing role, size and draft slot, no player-level link between engine *size*
# and these outcomes survives the false-discovery correction. A bigger engine alone does not win reps.
# The next section asks a different question: on a given play, how much of his *own* engine does the
# player use?

# %% [markdown]
# ## 6. Engine Utilization: how much of his own engine a player uses on a play
# On the A-S line, `a / A0 + v / S0 = 1` at any speed. For every frame we compute
# **U = a / A0 + v / S0** with the player's own in-game profile; U = 1 means he is on his personal
# limit, 0.6 means 60% of it. Per play we keep the peak U in the **first second after the snap**
# (launch), which precedes almost all pressures, and the peak U until the pass (max 2.5 s).
#
# Models are within-player (player fixed effects), so a player is only compared with himself:
# `outcome ~ U + role/route controls + player`, standard errors clustered by player.

# %%
import statsmodels.formula.api as smf  # noqa: E402

from nfl_bdb2027.build_features import play_table  # noqa: E402

if not os.path.exists(f"{CACHE}/plays.parquet"):
    prof = P[["A0_g", "S0_g"]].rename(columns={"A0_g": "A0", "S0_g": "S0"}).dropna()
    pd.concat([play_table(f, prof) for f in sorted(glob.glob(f"{DATA}/game_tracking_*.csv"))]).to_parquet(
        f"{CACHE}/plays.parquet")
plays = pd.read_parquet(f"{CACHE}/plays.parquet")
pp2 = pd.read_csv(find("player_play.csv"), usecols=pp_cols + ["blitzing", "target"])
pp2 = pp2[pp2.play_nullified_by_penalty != "Y"]
D = pp2.merge(plays, on=["game_id", "play_id", "nfl_id"])
D = D[D.util_launch.between(0, 1.3) & (D.frames >= 11)]  # at least 1 s tracked before any pass
print(f"{len(D):,} player-plays; median launch U {D.util_launch.median():.2f}, "
      f"median U to pass {D.util.median():.2f}")


def within_player(df, y, x, controls=""):
    used = [y, x, "nfl_id"] + [c.strip()[2:-1] if c.strip().startswith("C(") else c.strip()
                                for c in controls.split("+") if c.strip()]
    df = df.dropna(subset=used).copy()
    df[x + "_w"] = df[x] - df.groupby("nfl_id")[x].transform("mean")
    f = f"{y} ~ {x}_w" + (f" + {controls}" if controls else "") + " + C(nfl_id)"
    m = smf.ols(f, df).fit(cov_type="cluster", cov_kwds={"groups": df.nfl_id})
    b, (lo, hi) = m.params[x + "_w"] * 0.1, m.conf_int().loc[x + "_w"] * 0.1
    return {"effect of +10 U-points": b, "lo": lo, "hi": hi, "p": m.pvalues[x + "_w"], "outcome mean": df[y].mean(),
            "plays": len(df), "players": df.nfl_id.nunique()}


rush = D[D.player_get_off.notna()].copy()
rush["pressure"] = rush.time_to_pressure.notna().astype(float)
rush = rush[~(rush.time_to_pressure <= 1.0)]  # keep pressures that come after the launch window
rush["blitzing"] = rush.blitzing.astype(float)
recv = D[D.route_ran.notna() & D.separation_at_pass_forward.notna()].copy()
recv["target"] = recv.target.astype(float)
blk = D[D.pressure_allowed.notna()].copy()
blk["pressure_allowed"] = blk.pressure_allowed.astype(float)

util_rows = {
    "Pass rusher: pressure (prob.)": within_player(rush, "pressure", "util_launch", "C(lined_up_position)"),
    "  same, + blitz flag (plays where recorded)": within_player(rush, "pressure", "util_launch",
                                                                 "C(lined_up_position) + blitzing"),
    "Pass rusher: get-off (s)": within_player(rush, "player_get_off", "util_launch", "C(lined_up_position)"),
    "Receiver: separation at throw (yd)": within_player(recv, "separation_at_pass_forward", "util_launch",
                                                        "C(route_ran) + time_to_pass"),
    "Receiver: targeted (prob.)": within_player(recv, "target", "util_launch", "C(route_ran) + time_to_pass"),
    "OL: pressure allowed (prob.)": within_player(blk, "pressure_allowed", "util_launch", "C(lined_up_position)"),
}
util_table = pd.DataFrame(util_rows).T
print(util_table.round(4).to_string())

# stability of the habit: split each player's games in two (players with 100+ rush snaps)
half = rush.game_id % 2
hm = rush.assign(h=half).groupby(["nfl_id", "h"]).util_launch.mean().unstack()
hm = hm[rush.groupby("nfl_id").size().reindex(hm.index) >= 100]
r_half = hm.corr().iloc[0, 1]
print(f"pass rushers' average launch U, split-half r = {r_half:.2f} "
      f"(reliability {spearman_brown(r_half):.2f}, n = {len(hm)})")

# does the Combine see the habit? (partial r, role/weight/draft removed)
hab = rush.groupby("nfl_id").agg(U=("util_launch", "mean"), n=("pressure", "size"),
                                 edge_share=("lined_up_position", lambda x: (x == "EDGE").mean()))
hab = hab[hab.n >= 100].join(P[["combine_weight", "log_pick", "S0_c", "A0_c", "forty", "A0_g", "S0_g"]])
for x in ["forty", "S0_c", "A0_c"]:
    z = hab[["U", x, "combine_weight", "log_pick", "edge_share"]].dropna()
    c = ["combine_weight", "log_pick", "edge_share"]
    rr, lo, hi, n = boot_ci(resid(z, "U", c), resid(z, x, c))
    print(f"habit U vs {x}: partial r = {rr:+.2f} [{lo:+.2f}, {hi:+.2f}], n = {n}")

# %%
fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.4), gridspec_kw={"width_ratios": [1, 1.1]})
ax = axes[0]
vv = np.linspace(0, 10, 50)
A0e, S0e = 8.5, 10.0
for u, a in [(1.0, 1), (0.8, 0.6), (0.6, 0.35)]:
    ax.plot(vv, A0e * (u - vv / S0e), color=COL[0], alpha=a, lw=2.2 if u == 1 else 1.5)
    ax.text(0.2, A0e * u + 0.15, f"U = {u:.0%}" if u < 1 else "U = 100%: his own limit", color=COL[0], alpha=max(a, 0.6),
            fontsize=9.5)
ax.set(xlim=(0, 10.5), ylim=(0, 9.5), xlabel="Speed (yd/s)", ylabel="Acceleration (yd/s²)",
       title="Engine Utilization: distance to his own A-S line")
ax = axes[1]
rush["U_w"] = rush.util_launch - rush.groupby("nfl_id").util_launch.transform("mean")
rush["band"] = pd.qcut(rush.U_w, 5, labels=["lowest", "2", "3", "4", "highest"])
blk["U_w"] = blk.util_launch - blk.groupby("nfl_id").util_launch.transform("mean")
blk["band"] = pd.qcut(blk.U_w, 5, labels=["lowest", "2", "3", "4", "highest"])
x = np.arange(5)
a1 = rush.groupby("band", observed=True).pressure.mean() * 100
a2 = blk.groupby("band", observed=True).pressure_allowed.mean() * 100
ax.bar(x - 0.2, a1, 0.4, color=COL[1], label="Pass rusher: pressure generated")
ax.bar(x + 0.2, a2, 0.4, color=COL[4], label="Offensive lineman: pressure allowed")
for xi, v in zip(x - 0.2, a1):
    ax.text(xi, v + 0.2, f"{v:.1f}", ha="center", fontsize=9, color=INK2)
for xi, v in zip(x + 0.2, a2):
    ax.text(xi, v + 0.2, f"{v:.1f}", ha="center", fontsize=9, color=INK2)
ax.set_xticks(x, ["lowest", "2", "3", "4", "highest"])
ax.set(xlabel="Launch U relative to the player's own average (quintile)", ylabel="% of plays",
       title="Same player, different plays: using more engine at launch")
ax.legend(loc="upper left", fontsize=9)
fig.tight_layout()
save(fig, "fig4_utilization")

# %% [markdown]
# ## 7. The Rookie Engine Card (weekly)
# One page per rookie, updated after every game: the Combine engine (prior), the engine shown in
# games so far, and how much of it he uses at the snap, week by week.

# %%
cand = hab.join(P[["display_name", "combine_position", "games"]]).dropna(subset=["S0_c", "A0_c"])
pid = cand.sort_values("n", ascending=False).index[0]
row = P.loc[pid]
env = robust_envelope(gbins[gbins.nfl_id == pid], ["nfl_id"], k=2)
wk = rush[rush.nfl_id == pid].merge(games[["game_id", "season", "week"]], on="game_id")
weekly = wk.groupby(["season", "week"]).agg(U=("util_launch", "mean"), n=("pressure", "size"),
                                            pressure=("pressure", "mean")).reset_index()
weekly["label"] = weekly.season.astype(str).str[-2:] + "-W" + weekly.week.astype(str)

fig, axes = plt.subplots(1, 2, figsize=(12, 4.4), gridspec_kw={"width_ratios": [1, 1.4]})
ax = axes[0]
ax.scatter((env.bin + 0.5) * BIN, env.acc_max, s=12, color=MUTED, label="best accelerations in games")
vv = np.linspace(0, 12, 50)
ax.plot(vv, np.clip(row.A0_g * (1 - vv / row.S0_g), 0, None), color=COL[0], label=f"game engine: A0 {row.A0_g:.1f}, S0 {row.S0_g:.1f}")
ax.plot(vv, np.clip(row.A0_c * (1 - vv / row.S0_c), 0, None), color=COL[1], ls="--",
        label=f"Combine 40 engine: A0 {row.A0_c:.1f}, S0 {row.S0_c:.1f}")
ax.set(xlabel="Speed (yd/s)", ylabel="Acceleration (yd/s²)", ylim=(0, None), xlim=(0, 12),
       title=f"{row.display_name} ({row.combine_position}, {int(row.draft_year)} class)")
ax.legend(fontsize=8.5, loc="upper right")
ax = axes[1]
ax.bar(range(len(weekly)), weekly.U * 100, color=np.where(weekly.U < hab.loc[pid, "U"] - 0.03, COL[7], COL[0]), alpha=0.8)
ax.axhline(hab.loc[pid, "U"] * 100, color=INK2, ls="--", lw=1.2, label="his average")
ax.axhline(hab.U.mean() * 100, color=COL[3], ls=":", lw=1.5, label="all rookie rushers")
step = max(1, len(weekly) // 12)
ax.set_xticks(range(0, len(weekly), step), weekly.label[::step], rotation=45, ha="right", fontsize=8.5)
ax.set(ylabel="Launch U, % of his engine", ylim=(30, None),
       title="Weekly launch utilization (red: 3+ points below his norm)")
ax.legend(fontsize=8.5, loc="lower right")
fig.tight_layout()
save(fig, "fig5_engine_card")
