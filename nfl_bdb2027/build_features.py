"""Turn the raw competition CSVs into compact per-player movement tables.

    python -m nfl_bdb2027.build_features DATA_DIR OUT_DIR

Writes (all small):
  game_bins.parquet      per player x game x speed bin: best acceleration, hardest braking, frames
  game_speed.parquet     per player x game: frames tracked, top speed
  combine_bins.parquet   per player x drill attempt x speed bin (all Combine drills)
  combine_sprints.parquet  one mono-exponential fit per 40-yard-dash attempt
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from nfl_bdb2027.movement import binned_extremes, fit_sprint, signed_accel, speed_bin, turn_rate, utilization

KEYS = ["game_id", "play_id", "nfl_id"]


def seconds(iso):
    t = pd.to_datetime(iso)
    return (t - pd.Timestamp("2020-01-01")).dt.total_seconds().to_numpy()


def game_tables(path):
    cols = ["game_id", "play_id", "nfl_id", "time", "s"]
    df = pd.read_csv(path, usecols=cols, dtype={"s": "float32"})
    df["t"] = seconds(df.pop("time"))
    df = df.sort_values(KEYS + ["t"], kind="stable").reset_index(drop=True)
    df["s_smooth"], df["acc"] = signed_accel(df, KEYS)
    # physically impossible values are sensor glitches, not athletes
    df.loc[df["acc"].abs() > 12, "acc"] = np.nan
    bins = binned_extremes(df, ["nfl_id", "game_id"])
    speed = df.groupby(["nfl_id", "game_id"]).agg(frames=("s", "size"), plays=("play_id", "nunique"),
                                                  top_speed=("s_smooth", "max"))
    return bins, speed.reset_index()


def play_table(path, profiles, window=2.5, launch=1.0):
    """Per player-play movement from the snap until the pass is thrown or `window` seconds pass.

    `util_launch` is the peak utilization in the first `launch` seconds only, which comes before
    almost every pressure and so can be read as a cause rather than a consequence of the play.

    `profiles` is indexed by nfl_id with columns A0 and S0 (the player's in-game profile). Returns
    peak utilization of that profile, peak speed and peak acceleration in the window, plus the time
    from snap to the pass (if any).
    """
    cols = ["game_id", "play_id", "nfl_id", "time", "s", "event"]
    df = pd.read_csv(path, usecols=cols, dtype={"s": "float32"})
    df["t"] = seconds(df.pop("time"))
    df = df.sort_values(KEYS + ["t"], kind="stable").reset_index(drop=True)
    df["s_smooth"], df["acc"] = signed_accel(df, KEYS)
    df.loc[df["acc"].abs() > 12, "acc"] = np.nan
    snap = df[df.event == "ball_snap"].groupby(KEYS).t.min().rename("t_snap")
    throw = df[df.event == "pass_forward"].groupby(KEYS).t.min().rename("t_pass")
    df = df.join(snap, on=KEYS).join(throw, on=KEYS)
    end = np.fmin(df.t_snap + window, df.t_pass)  # fmin ignores a missing pass time
    df = df[(df.t >= df.t_snap) & (df.t <= end + 1e-6)]
    prof = profiles.reindex(df.nfl_id.to_numpy())
    df["u"] = utilization(df.s_smooth, df.acc, prof.A0.to_numpy(), prof.S0.to_numpy())
    df["u_launch"] = df.u.where(df.t <= df.t_snap + launch + 1e-6)
    out = df.groupby(KEYS).agg(util=("u", "max"), util_launch=("u_launch", "max"),
                               peak_speed=("s_smooth", "max"), peak_acc=("acc", "max"),
                               frames=("u", "size"), t_snap=("t_snap", "first"), t_pass=("t_pass", "first"))
    out["time_to_pass"] = out.pop("t_pass") - out.pop("t_snap")
    return out.reset_index()


def lateral_bins(df, keys, unit):
    """Per player x unit (game or drill attempt) x speed bin: hardest sideways acceleration.

    Sideways (centripetal) acceleration = speed x turn rate. Values above 15 yd/s^2 are tracking
    glitches (heading jumps), not athletes, and are dropped.
    """
    df = df.assign(omega=turn_rate(df, keys))
    df["lat"] = (df["s_smooth"] * df["omega"]).abs()
    df.loc[df["lat"] > 15, "lat"] = np.nan
    d = df[["nfl_id", unit, "s_smooth", "lat"]].dropna()
    d = d.assign(bin=speed_bin(d["s_smooth"]))
    return d.groupby(["nfl_id", unit, "bin"]).lat.agg(lat_max="max", n="size").reset_index()


def game_lateral(path, exclude=None):
    """Lateral envelope per player-game. Plays listed in `exclude` (game_id/play_id/nfl_id), e.g.
    the player's own targets, are left out so ball-carrying moves cannot inflate the envelope."""
    df = pd.read_csv(path, usecols=["game_id", "play_id", "nfl_id", "time", "s", "dir"],
                     dtype={"s": "float32", "dir": "float32"})
    if exclude is not None:
        df = df.merge(exclude[KEYS].drop_duplicates(), on=KEYS, how="left", indicator=True)
        df = df[df.pop("_merge") == "left_only"]
    df["t"] = seconds(df.pop("time"))
    df = df.sort_values(KEYS + ["t"], kind="stable").reset_index(drop=True)
    df["s_smooth"], _ = signed_accel(df, KEYS)
    return lateral_bins(df, KEYS, "game_id")


def route_table(path, plays, envelope):
    """Per route: hardest sideways acceleration from the snap to the pass, absolute and as a share of
    the player's own turning envelope at that speed.

    `plays` holds the game_id/play_id/nfl_id of the routes to score; `envelope` is indexed by
    (nfl_id, bin) with column lat_max (the player's best sideways acceleration at each speed).
    """
    df = pd.read_csv(path, usecols=["game_id", "play_id", "nfl_id", "time", "s", "dir", "event"],
                     dtype={"s": "float32", "dir": "float32"})
    df = df.merge(plays[KEYS], on=KEYS)
    df["t"] = seconds(df.pop("time"))
    df = df.sort_values(KEYS + ["t"], kind="stable").reset_index(drop=True)
    df["s_smooth"], _ = signed_accel(df, KEYS)
    df["lat"] = (df["s_smooth"] * turn_rate(df, KEYS)).abs()
    df.loc[df["lat"] > 15, "lat"] = np.nan
    snap = df[df.event == "ball_snap"].groupby(KEYS).t.min().rename("t_snap")
    throw = df[df.event == "pass_forward"].groupby(KEYS).t.min().rename("t_pass")
    df = df.join(snap, on=KEYS).join(throw, on=KEYS)
    df = df[(df.t >= df.t_snap) & (df.t <= df.t_pass + 1e-6)]
    cap = envelope.lat_max.reindex(pd.MultiIndex.from_arrays([df.nfl_id, speed_bin(df.s_smooth)])).to_numpy()
    df["lat_share"] = df["lat"] / cap
    out = df.groupby(KEYS).agg(lat_peak=("lat", "max"), lat_share=("lat_share", "max"),
                               speed_peak=("s_smooth", "max"), frames=("t", "size"))
    return out.reset_index()


def combine_lateral(path):
    df = pd.read_csv(path)
    df = df[df.entity_type == "PLAYER"].copy()
    df["t"] = seconds(df["time"])
    keys = ["nfl_id", "event_id"]
    df = df.sort_values(keys + ["t"], kind="stable").reset_index(drop=True)
    df["s_smooth"], _ = signed_accel(df, keys)
    out = lateral_bins(df, keys, "event_id")
    drills = df.groupby(keys)[["drill_type", "drill_name"]].first().reset_index()
    return out.merge(drills, on=keys)


def combine_tables(path):
    df = pd.read_csv(path)
    df = df[df.entity_type == "PLAYER"].copy()
    df["t"] = seconds(df["time"])
    keys = ["nfl_id", "event_id"]
    df = df.sort_values(keys + ["t"], kind="stable").reset_index(drop=True)
    df["s_smooth"], df["acc"] = signed_accel(df, keys)
    df.loc[df["acc"].abs() > 12, "acc"] = np.nan
    bins = binned_extremes(df, ["nfl_id", "event_id"])
    drills = df.groupby(keys)[["drill_type", "drill_name", "attempt", "draft_year"]].first()
    bins = bins.merge(drills.reset_index(), on=keys)

    rows = []
    sprint = df[df.drill_type == "FORTY_YARD_DASH"]
    for (pid, ev), d in sprint.groupby(keys, sort=False):
        fit = fit_sprint(d["t"].to_numpy() - d["t"].iloc[0], d["s"].to_numpy())
        x = d["x"].to_numpy()
        fit.update(nfl_id=pid, event_id=ev, attempt=d["attempt"].iloc[0], frames=len(d),
                   distance=float(np.abs(x[-1] - x[0])), peak_speed=float(d["s"].max()))
        rows.append(fit)
    return bins, pd.DataFrame(rows)


def main(data_dir, out_dir):
    data_dir, out_dir = Path(data_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cb, sprints = combine_tables(data_dir / "combine_tracking.csv")
    cb.to_parquet(out_dir / "combine_bins.parquet")
    sprints.to_parquet(out_dir / "combine_sprints.parquet")
    print("combine:", len(cb), "bin rows,", len(sprints), "sprints")
    all_bins, all_speed = [], []
    for f in sorted(data_dir.glob("game_tracking_*.csv")):
        b, s = game_tables(f)
        all_bins.append(b)
        all_speed.append(s)
        print(f.name, len(b), "bin rows,", len(s), "player-games")
    pd.concat(all_bins).to_parquet(out_dir / "game_bins.parquet")
    pd.concat(all_speed).to_parquet(out_dir / "game_speed.parquet")


if __name__ == "__main__":
    main(*sys.argv[1:3])
