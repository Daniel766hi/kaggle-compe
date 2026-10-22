# %% [markdown]
# # Bend, Don't Brake: the turning engine the Combine cannot see
#
# Companion notebook for our second NFL Big Data Bowl 2027 writeup. Every number and figure in the
# writeup is produced here from the competition data.
#
# **Idea.** Straight-line speed is well measured at the Combine. Turning is not. When a player runs a
# curved path, he needs sideways (centripetal) acceleration `a_c = v * omega` (speed times turn rate).
# Like a car's tyres, every athlete has a limit on how much sideways acceleration he can produce at
# each speed. We measure that **turning envelope** from game tracking and from Combine drills, then ask:
# 1. Is in-game turning a stable trait, and how many games until we know it?
# 2. Does any Combine drill or time reveal it?
# 3. Does it matter for receivers (separation, yards after catch)?

# %%
import glob
import os
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests

warnings.filterwarnings("ignore")
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 40)

# INLINE: nfl_bdb2027
from nfl_bdb2027.build_features import KEYS, combine_lateral, game_lateral, game_tables  # noqa: E402
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


def resid(df, y, ctrl):
    X = pd.get_dummies(df[ctrl], drop_first=True, dtype=float) if ctrl else None
    if X is None or X.shape[1] == 0:
        return df[y] - df[y].mean()
    return sm.OLS(df[y].astype(float), sm.add_constant(X)).fit().resid


def partial_r(df, y, x, ctrl, n_boot=2000, seed=0):
    """Partial correlation with a player-bootstrap 95% interval and a t-test p-value."""
    from scipy import stats
    d = df[[y, x] + ctrl].dropna()
    ry, rx = resid(d, y, ctrl).to_numpy(), resid(d, x, ctrl).to_numpy()
    r = np.corrcoef(rx, ry)[0, 1]
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(d), (n_boot, len(d)))
    a, b = rx[idx] - rx[idx].mean(1, keepdims=True), ry[idx] - ry[idx].mean(1, keepdims=True)
    bs = (a * b).sum(1) / np.sqrt((a ** 2).sum(1) * (b ** 2).sum(1))
    dof = len(d) - 2 - len(ctrl)
    p = 2 * stats.t.sf(abs(r * np.sqrt(dof / (1 - r ** 2))), dof)
    lo, hi = np.percentile(bs, [2.5, 97.5])
    return {"r": r, "lo": lo, "hi": hi, "n": len(d), "p": p}


def grip(env, lo=3.0, hi=7.0, col="lat_max"):
    """Turning grip: mean of the sideways-acceleration envelope between lo and hi yd/s.

    Only players whose envelope covers every bin in the band get a value."""
    v = (env.bin + 0.5) * BIN
    e = env[(v >= lo) & (v < hi)]
    full = e.groupby("nfl_id").bin.size() == int(round((hi - lo) / BIN))
    return e.groupby("nfl_id")[col].mean()[full]


# %% [markdown]
# ## 0. Data
# For every player x game and every 0.25 yd/s speed bin we keep the hardest sideways acceleration
# (speed x turn rate, from the motion direction). Plays where the player was targeted or carried the
# ball are **left out**, so evasive moves with the ball cannot inflate a receiver's turning grip that we
# later relate to yards after catch. The same is done for every Combine drill attempt.

# %%
DATA = os.path.dirname(find("players.csv"))
CACHE = os.environ.get("FEATURE_DIR", "/kaggle/working/features2")
os.makedirs(CACHE, exist_ok=True)
pp_cols = KEYS + ["lined_up_position", "route_ran", "separation_at_pass_forward", "target", "rec_yards",
                  "rush_yards", "yards_after_catch", "expected_yards_after_catch", "play_nullified_by_penalty"]
pp = pd.read_csv(find("player_play.csv"), usecols=pp_cols)
ball = pp[(pp.target == True) | pp.rec_yards.notna() | pp.rush_yards.notna()]  # noqa: E712
tracking_files = sorted(glob.glob(f"{DATA}/game_tracking_*.csv"))
if not os.path.exists(f"{CACHE}/game_lat.parquet"):
    pd.concat([game_lateral(f, ball) for f in tracking_files]).to_parquet(f"{CACHE}/game_lat.parquet")
    combine_lateral(f"{DATA}/combine_tracking.csv").to_parquet(f"{CACHE}/combine_lat.parquet")
    bins, speed = zip(*[game_tables(f) for f in tracking_files])
    pd.concat(bins).to_parquet(f"{CACHE}/game_bins.parquet")
glat = pd.read_parquet(f"{CACHE}/game_lat.parquet").reset_index(drop=True)
clat = pd.read_parquet(f"{CACHE}/combine_lat.parquet")
gbins = pd.read_parquet(f"{CACHE}/game_bins.parquet").reset_index(drop=True)
players = pd.read_csv(f"{DATA}/players.csv").set_index("nfl_id")
combine = pd.read_csv(f"{DATA}/combine_results.csv").set_index("nfl_id")
games = pd.read_csv(f"{DATA}/games.csv")

order = glat[["nfl_id", "game_id"]].drop_duplicates().sort_values(["nfl_id", "game_id"])
order["gi"] = order.groupby("nfl_id").cumcount() + 1
glat = glat.merge(order, on=["nfl_id", "game_id"])
n_games = order.groupby("nfl_id").gi.max().rename("games")
print(f"{len(ball):,} ball-in-hand or targeted player-plays excluded; "
      f"{n_games.size} rookies, {len(order):,} player-games")

# in-game straight-line profile (top speed S0, acceleration A0) used as a control
env_fw = robust_envelope(gbins, ["nfl_id"], k=2)
fw = pd.DataFrame({p: fit_as_profile(e.bin, e.acc_max) for p, e in env_fw.groupby("nfl_id")}).T.astype(float)

genv = robust_envelope(glat, ["nfl_id"], col="lat_max", k=2)
P = combine[["combine_position", "combine_weight", "forty", "three_cone", "short_shuttle"]].join(n_games)
P = P.join(grip(genv).rename("grip")).join(fw[["S0", "A0"]])
P = P.join(players[["display_name", "draft_overall_pick", "draft_year"]])
P["log_pick"] = np.log(P.draft_overall_pick.fillna(300))
print(P.groupby("combine_position")[["grip", "S0", "A0"]].median().round(2).loc[POS_ORDER])

# %% [markdown]
# ## 1. The turning envelope
# Per speed bin, the second-best sideways acceleration across games (one glitchy game cannot set it).
# Turning grip = the envelope averaged over 3-7 yd/s (the speeds of route breaks and pursuit angles).

# %%
genv["v"] = (genv.bin + 0.5) * BIN
genv = genv.join(P.combine_position, on="nfl_id")
fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.4), gridspec_kw={"width_ratios": [1.15, 1]})
ax = axes[0]
for pos in POS_ORDER:
    q = genv[genv.combine_position == pos].groupby("bin").lat_max
    v = (q.median().index + 0.5) * BIN
    ax.plot(v, q.median(), color=POS_COLOR[pos], label=pos)
    ax.fill_between(v, q.quantile(0.25), q.quantile(0.75), color=POS_COLOR[pos], alpha=0.12, lw=0)
ax.axvspan(3, 7, color=MUTED, alpha=0.25, lw=0)
ax.text(5, 0.4, "grip band", ha="center", color=INK2, fontsize=9)
ax.set(xlim=(1, 11), ylim=(0, None), xlabel="Speed (yd/s)", ylabel="Sideways acceleration (yd/s²)",
       title="Turning envelope by position (median, IQR)")
ax.legend(ncol=5, fontsize=9, loc="upper right")

# two receivers with almost the same top speed but very different grip
wr = P[(P.combine_position == "WR") & (P.games >= 16)].dropna(subset=["grip", "S0"])
wr = wr.assign(s_band=(wr.S0 * 4).round() / 4)
pair = None
for _, g in wr.groupby("s_band"):
    if len(g) >= 2 and (pair is None or g.grip.max() - g.grip.min() > pair[2]):
        pair = (g.grip.idxmax(), g.grip.idxmin(), g.grip.max() - g.grip.min())
ax = axes[1]
th = np.linspace(-np.pi / 2, np.pi / 2, 91)
for pid, c in zip(pair[:2], [COL[0], COL[1]]):
    fwd = env_fw[env_fw.nfl_id == pid]
    band = ((fwd.bin + 0.5) * BIN).between(3, 7)
    A = fwd[band].acc_max.mean()
    B = -robust_envelope(gbins[gbins.nfl_id == pid], ["nfl_id"], col="acc_min", k=2, highest=False).pipe(
        lambda e: e[((e.bin + 0.5) * BIN).between(3, 7)].acc_min.mean())
    L = P.loc[pid, "grip"]
    ax.plot(L * np.cos(th), A * np.sin(th).clip(0) + B * np.sin(th).clip(None, 0), color=c,
            label=f"{P.loc[pid, 'display_name']}: grip {L:.1f}, S0 {P.loc[pid, 'S0']:.1f}")
    ax.plot(-L * np.cos(th), A * np.sin(th).clip(0) + B * np.sin(th).clip(None, 0), color=c)
ax.axhline(0, color=INK2, lw=0.8)
ax.axvline(0, color=INK2, lw=0.8)
ax.set_aspect("equal")
ax.set(xlabel="Sideways (yd/s²)", ylabel="Braking  ←  → speeding up (yd/s²)",
       title="Same top speed, different turning (3-7 yd/s)")
ax.legend(fontsize=8.5, loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=1)
ax.text(0.99, 0.01, "curves drawn through the three\nmeasured limits", transform=ax.transAxes,
        ha="right", va="bottom", fontsize=8, color=INK2)
fig.tight_layout()
save(fig, "fig1_turning_envelope")

# %% [markdown]
# ## 2. A stable trait, learned fast
# Split-half reliability across games, then: for rookies with 16+ games, how well does the grip from
# only the first k games predict the grip shown in games 9 onward (within position)?

# %%
many = P.index[P.games >= 8]
sh = split_half(glat[glat.nfl_id.isin(many)], "nfl_id", "game_id",
                lambda d: grip(robust_envelope(d, ["nfl_id"], col="lat_max", k=2)).mean())
sh = sh.dropna()
r_half = np.corrcoef(sh.half_a, sh.half_b)[0, 1]
print(f"turning grip split-half r = {r_half:.2f}, reliability {spearman_brown(r_half):.2f}, n = {len(sh)}")

ids = P.index[(P.games >= 16) & P.grip.notna()]
gk = glat[glat.nfl_id.isin(ids)]
late = grip(robust_envelope(gk[gk.gi > 8], ["nfl_id"], col="lat_max", k=2)).rename("late")
K = [1, 2, 3, 4, 6, 8]
stab = []
for k in K:
    early = grip(robust_envelope(gk[gk.gi <= k], ["nfl_id"], col="lat_max", k=min(2, k))).rename("early")
    d = pd.concat([early, late, P.combine_position], axis=1).dropna()
    rr = np.corrcoef(resid(d, "early", ["combine_position"]), resid(d, "late", ["combine_position"]))[0, 1]
    stab.append({"k": k, "r": rr, "n": len(d)})
stab = pd.DataFrame(stab)
print(stab.round(2).to_string(index=False))

# %% [markdown]
# ## 3. Can the Combine see it?
# Candidates, each correlated with in-game grip *within position* for rookies with 8+ games:
# official 3-cone and short-shuttle times, the 40, the hardest sideways acceleration in the agility
# drills (3-cone, shuttle) and in the position drills, and for WRs a route-drill composite (mean
# z-score of peak sideways acceleration across the route drills he ran).

# %%
v = (clat.bin + 0.5) * BIN
fam = clat.drill_type.map({"FORTY_YARD_DASH": "forty", "THREE_CONE_DRILL": "agility",
                           "SHORT_SHUTTLE": "agility"}).fillna("position")
peak = clat[v >= 2].assign(fam=fam).groupby(["nfl_id", "fam"]).lat_max.max().unstack()
P["agility_drill_peak"] = peak.get("agility")
P["position_drill_peak"] = peak.get("position")
wr_drills = clat[(v >= 2) & (clat.drill_type == "SKILL_DRILLS_WR") & clat.drill_name.str.contains("ROUTE")]
wpk = wr_drills.groupby(["nfl_id", "drill_name"]).lat_max.max().unstack()
z = (wpk - wpk.mean()) / wpk.std()
P["route_drill_composite"] = z.mean(axis=1).where(z.notna().sum(axis=1) >= 4)

CANDIDATES = {"3-cone time (faster)": "three_cone", "Short shuttle (faster)": "short_shuttle",
              "40 time (faster)": "forty", "Agility-drill peak": "agility_drill_peak",
              "Position-drill peak": "position_drill_peak", "WR route-drill composite": "route_drill_composite"}
d8 = P[P.games >= 8].copy()
for c in ["three_cone", "short_shuttle", "forty"]:
    d8[c] = -d8[c]
see = []
for pos in POS_ORDER:
    q = d8[d8.combine_position == pos]
    for name, x in CANDIDATES.items():
        if q[[x, "grip"]].dropna().shape[0] >= 15:
            res = partial_r(q, "grip", x, ["combine_weight"])
            see.append({"position": pos, "Combine measure": name, **res})
see = pd.DataFrame(see)
see["q"] = multipletests(see.p, method="fdr_bh")[1]
print(see.round(2).to_string(index=False))

# %% [markdown]
# Route by route: is a WR's peak sideways acceleration in a Combine route drill a guide to his game
# routes of the same shape? (median peak per route type, WRs with 10+ such routes, before the throw)

# %%
from nfl_bdb2027.build_features import route_table  # noqa: E402

if not os.path.exists(f"{CACHE}/routes.parquet"):
    rplays = pp[pp.route_ran.notna()]
    pd.concat([route_table(f, rplays, genv.set_index(["nfl_id", "bin"])[["lat_max"]]) for f in tracking_files]
              ).to_parquet(f"{CACHE}/routes.parquet")
routes = pd.read_parquet(f"{CACHE}/routes.parquet").merge(pp[KEYS + ["route_ran"]], on=KEYS)
game_route = routes.groupby(["nfl_id", "route_ran"]).lat_peak.median().unstack()
game_route = game_route.where(routes.groupby(["nfl_id", "route_ran"]).size().unstack() >= 10)
MATCH = {"CURL_ROUTE_RIGHT": "HITCH", "COMEBACK_ROUTE_RIGHT": "HITCH", "SPEED_OUT_ROUTE_LEFT": "OUT",
         "DAGGER_ROUTE_LEFT": "IN", "SLOT_STRIKE_ROUTE_LEFT": "IN", "POST_CORNER_ROUTE_RIGHT": "CORNER",
         "SLOT_SAIL_ROUTE_RIGHT": "CORNER", "GO_ROUTE_RIGHT": "GO"}
match_rows = []
for drill, route in MATCH.items():
    m = pd.concat([wpk.get(drill), game_route.get(route), P.combine_position], axis=1).dropna()
    m = m[m.combine_position == "WR"]
    if len(m) >= 15:
        match_rows.append({"Combine drill": drill, "game route": route, "n": len(m),
                           "r": m.iloc[:, 0].corr(m.iloc[:, 1])})
print(pd.DataFrame(match_rows).round(2).to_string(index=False))

# %%
fig, ax = plt.subplots(figsize=(11, 4.6))
names = list(CANDIDATES)
for i, pos in enumerate(POS_ORDER):
    q = see[see.position == pos].set_index("Combine measure").reindex(names)
    y = np.arange(len(names)) + (i - 2) * 0.15
    ok = q.r.notna()
    ax.errorbar(q.r[ok], y[ok.to_numpy()], xerr=[(q.r - q.lo)[ok], (q.hi - q.r)[ok]], fmt="o", ms=5,
                color=POS_COLOR[pos], label=f"{pos}", lw=1.3)
ax.axvline(0, color=INK2, lw=1)
ax.set_yticks(range(len(names)), names)
ax.invert_yaxis()
ax.set(xlabel="Partial correlation with in-game turning grip (body weight removed; 95% bootstrap CI)",
       title="No Combine measure reliably reveals how a skill player turns in games")
ax.legend(ncol=5, loc="lower center", bbox_to_anchor=(0.5, 1.06), fontsize=9)
ax.set_title("No Combine measure reliably reveals how a skill player turns in games", pad=34)
fig.tight_layout()
save(fig, "fig2_combine_blind_spot")

# %% [markdown]
# ## 4. Does turning grip matter for receivers?
# Player-level outcomes on non-penalty plays:
# - **Route-adjusted separation** at the throw (separation minus the average for that route type),
#   players with 100+ routes.
# - **Yards after catch over expected** (YAC minus NGS expected YAC), players with 20+ catches.
#
# Partial correlations remove body weight, draft slot (log pick) and slot share. We compare grip with
# the straight-line traits (in-game S0, A0) and the Combine times. Benjamini-Hochberg q-values over all
# tests in the table.

# %%
pp = pp[pp.play_nullified_by_penalty != "Y"]
r = pp[pp.separation_at_pass_forward.notna() & pp.route_ran.notna()].copy()
r["sep_adj"] = r.separation_at_pass_forward - r.groupby("route_ran").separation_at_pass_forward.transform("mean")
c = pp[pp.yards_after_catch.notna() & pp.expected_yards_after_catch.notna()].copy()
c["yacoe"] = c.yards_after_catch - c.expected_yards_after_catch
R = P.join(r.groupby("nfl_id").agg(sep_adj=("sep_adj", "mean"), routes=("sep_adj", "size"),
                                   slot_share=("lined_up_position", lambda x: x.isin(["SLOT_WR", "TE"]).mean())))
R = R.join(c.groupby("nfl_id").agg(yacoe=("yacoe", "mean"), catches=("yacoe", "size")))
for col in ["forty", "three_cone"]:
    R[col] = -R[col]

TRAITS = {"Turning grip (games)": "grip", "Top speed S0 (games)": "S0", "Acceleration A0 (games)": "A0",
          "40 time (faster)": "forty", "3-cone (faster)": "three_cone"}
rows = []
ctrl = ["combine_weight", "log_pick", "slot_share"]
for pos, minimum in [("WR", None), ("TE", None)]:
    for out, (ycol, ncol, mn) in {"Route-adjusted separation": ("sep_adj", "routes", 100),
                                  "YAC over expected": ("yacoe", "catches", 20)}.items():
        q = R[(R.combine_position == pos) & (R[ncol] >= mn)]
        for name, x in TRAITS.items():
            if q[[ycol, x]].dropna().shape[0] >= 15:
                rows.append({"position": pos, "outcome": out, "trait": name, **partial_r(q, ycol, x, ctrl)})
link = pd.DataFrame(rows)
link["q"] = multipletests(link.p, method="fdr_bh")[1]
print(link.round(3).to_string(index=False))

# %%
fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.4))
q = R[(R.combine_position == "WR") & (R.routes >= 100)].dropna(subset=["grip", "sep_adj"] + ctrl)
for ax, (ycol, lab, d) in zip(axes, [("sep_adj", "Route-adjusted separation (yd)", q),
                                     ("yacoe", "YAC over expected (yd)",
                                      R[(R.combine_position == "WR") & (R.catches >= 20)].dropna(
                                          subset=["grip", "yacoe"] + ctrl))]):
    rx, ry = resid(d, "grip", ctrl), resid(d, ycol, ctrl)
    ax.scatter(rx, ry, s=22, color=COL[0], alpha=0.7)
    b = np.polyfit(rx, ry, 1)
    xs = np.linspace(rx.min(), rx.max(), 20)
    ax.plot(xs, np.polyval(b, xs), color=COL[1])
    st = link[(link.position == "WR") & (link.trait == "Turning grip (games)") &
              (link.outcome == ("Route-adjusted separation" if ycol == "sep_adj" else "YAC over expected"))].iloc[0]
    ax.set(xlabel="Turning grip, relative to similar WRs (yd/s²)", ylabel=lab,
           title=f"WRs: partial r = {st.r:+.2f} [{st.lo:+.2f}, {st.hi:+.2f}], n = {st.n}")
fig.tight_layout()
save(fig, "fig3_grip_outcomes")

# %% [markdown]
# ## 5. The Turning Card (weekly)
# For each rookie receiver, after every game: his turning envelope so far against the position band,
# and his weekly grip (best two games so far vs. that single game) with how far it has stabilised.

# %%
cand = R[(R.combine_position == "WR") & (R.games >= 30)].dropna(subset=["grip"])
pid = cand.grip.idxmax()
row = P.loc[pid]
gp = glat[glat.nfl_id == pid].merge(games[["game_id", "season", "week", "season_type"]], on="game_id")
per_game = (gp.groupby("gi").apply(lambda d: grip(d).reindex([pid]).iloc[0], include_groups=False)
            .rename("grip_game").reset_index()
            .merge(gp[["gi", "season", "week"]].drop_duplicates(), on="gi"))
running = [grip(robust_envelope(gp[gp.gi <= k], ["nfl_id"], col="lat_max", k=min(2, k))).reindex([pid]).iloc[0]
           for k in per_game.gi]
per_game["grip_running"] = running
band = genv[genv.combine_position == "WR"].groupby("bin").lat_max

fig, axes = plt.subplots(1, 2, figsize=(12, 4.4), gridspec_kw={"width_ratios": [1, 1.4]})
ax = axes[0]
vv = (band.median().index + 0.5) * BIN
ax.fill_between(vv, band.quantile(0.1), band.quantile(0.9), color=MUTED, alpha=0.4, lw=0, label="WR 10th-90th pct")
mine = genv[genv.nfl_id == pid]
ax.plot(mine.v, mine.lat_max, color=COL[0], label=row.display_name)
ax.set(xlim=(0, 11), ylim=(0, None), xlabel="Speed (yd/s)", ylabel="Sideways acceleration (yd/s²)",
       title=f"{row.display_name} (WR, {int(row.draft_year)} class): turning envelope")
ax.legend(fontsize=9)
ax = axes[1]
x = np.arange(len(per_game))
ax.bar(x, per_game.grip_game, color=COL[0], alpha=0.35, label="single-game grip")
ax.plot(x, per_game.grip_running, color=COL[0], label="grip shown so far (2nd-best game)")
ax.axhline(P.loc[P.combine_position == "WR", "grip"].median(), color=COL[3], ls=":", lw=1.6, label="WR median")
k_ok = stab.loc[stab.r >= 0.5, "k"].min()
if pd.notna(k_ok):
    ax.axvspan(-0.5, k_ok - 0.5, color=MUTED, alpha=0.3, lw=0)
    ax.text(k_ok / 2 - 0.5, ax.get_ylim()[1] * 0.97, "early\nestimate", ha="center", va="top", fontsize=8.5,
            color=INK2)
labels = per_game.season.astype(str).str[-2:] + "-W" + per_game.week.astype(str)
step = max(1, len(per_game) // 12)
ax.set_xticks(x[::step], labels[::step], rotation=45, ha="right", fontsize=8.5)
ax.set(ylabel="Grip (yd/s²)", ylim=(0, None), title="Weekly turning grip")
ax.legend(fontsize=8.5, loc="lower right")
fig.tight_layout()
save(fig, "fig4_turning_card")
