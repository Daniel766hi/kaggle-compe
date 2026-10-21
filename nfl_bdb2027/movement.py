"""Movement profiles from 10 Hz tracking: sprint fits, acceleration-speed (A-S) profiles.

Speeds are in yards/second, accelerations in yards/second^2, as in the tracking data.

The idea: the 40-yard dash and the in-game "in-situ" A-S profile (Morin et al. 2021) describe the
same two numbers. A mono-exponential sprint v(t) = S0 * (1 - exp(-t / tau)) (Samozino et al. 2016)
has acceleration a = (S0 - v) / tau, a straight line in the speed-acceleration plane that starts at
A0 = S0 / tau and reaches zero at S0. The in-game profile fits the same line to the best
accelerations a player produced at each speed during games, so the two can be compared directly.
"""

import numpy as np
import pandas as pd

DT = 0.1  # seconds between tracking frames
BIN = 0.25  # speed bin width, yd/s
N_BINS = 52  # bins cover 0 to 13 yd/s


def signed_accel(frames, keys, speed="s", time="t"):
    """Tangential acceleration (change in speed per second) within each tracked sequence.

    The provided `a` column is a magnitude, so braking and speeding up look alike; the derivative
    of speed keeps the sign. Frames must be sorted by keys then time. Speed is smoothed with a
    centred 3-frame mean inside each sequence; frames after a time gap get NaN acceleration.
    Returns (smoothed speed, acceleration) as arrays aligned with `frames`.
    """
    key = frames[keys].ne(frames[keys].shift()).any(axis=1).cumsum().to_numpy()
    s = frames[speed].to_numpy(dtype=float)
    t = frames[time].to_numpy(dtype=float)
    same_prev = np.r_[False, key[1:] == key[:-1]]
    same_next = np.r_[key[:-1] == key[1:], False]
    prev = np.where(same_prev, np.r_[np.nan, s[:-1]], np.nan)
    nxt = np.where(same_next, np.r_[s[1:], np.nan], np.nan)
    smooth = np.nanmean(np.vstack([prev, s, nxt]), axis=0)
    dt = np.r_[np.nan, np.diff(t)]
    ok = same_prev & (np.abs(dt - DT) < 0.02)
    acc = np.where(ok, np.r_[np.nan, np.diff(smooth)] / DT, np.nan)
    return smooth, acc


def speed_bin(s):
    return np.clip((np.asarray(s) / BIN).astype(int), 0, N_BINS - 1)


def binned_extremes(df, keys, s="s_smooth", acc="acc"):
    """Per group and speed bin: best acceleration, hardest braking and frame count."""
    d = df[keys + [s, acc]].dropna()
    d = d.assign(bin=speed_bin(d[s]))
    out = d.groupby(keys + ["bin"], sort=False)[acc].agg(acc_max="max", acc_min="min", n="size")
    return out.reset_index()


def robust_envelope(per_unit, keys, col="acc_max", k=2, highest=True):
    """Combine per-game (or per-attempt) bin extremes into one envelope per player.

    Takes the k-th best value across units in each bin, so a single sensor glitch in one game
    cannot set a player's profile. Bins seen in fewer than k units are dropped.
    """
    d = per_unit.reset_index(drop=True).sort_values(col, ascending=not highest)
    ranked = d.groupby(keys + ["bin"], sort=False)[col].nth(k - 1)
    env = d.loc[ranked.index, keys + ["bin", col]]
    return env.sort_values(keys + ["bin"]).reset_index(drop=True)


def fit_as_profile(bins, amax, min_speed=3.0, min_points=6, min_r2=0.5, max_s0=13.5):
    """Fit the linear A-S line a = A0 * (1 - v / S0) to the upper envelope (Morin et al. 2021).

    Uses bins from the speed at peak acceleration (and at least `min_speed`) upward, where the
    envelope is limited by the athlete's capacity rather than by how a play started.
    Fits that explain little (r2 < min_r2) or extrapolate to an impossible top speed (> max_s0 yd/s,
    about 27.6 mph) come from too little data and are rejected.
    Returns dict(A0, S0, r2, n) or NaNs if the fit is not possible.
    """
    v = (np.asarray(bins) + 0.5) * BIN
    a = np.asarray(amax, dtype=float)
    ok = np.isfinite(a) & (a > 0)
    v, a = v[ok], a[ok]
    nan = {"A0": np.nan, "S0": np.nan, "r2": np.nan, "n": 0}
    if len(v) < min_points:
        return nan
    start = max(min_speed, v[np.argmax(a)])
    m = v >= start
    v, a = v[m], a[m]
    if len(v) < min_points:
        return nan
    slope, icept = np.polyfit(v, a, 1)
    if slope >= 0:
        return nan
    pred = icept + slope * v
    ss = ((a - a.mean()) ** 2).sum()
    r2 = 1 - ((a - pred) ** 2).sum() / ss if ss > 0 else np.nan
    if not r2 >= min_r2 or -icept / slope > max_s0:
        return nan
    return {"A0": icept, "S0": -icept / slope, "r2": r2, "n": int(len(v))}


def fit_sprint(t, s):
    """Fit v(t) = S0 * (1 - exp(-(t - t0) / tau)) to one sprint's speed trace.

    `t` in seconds from any origin, `s` in yd/s. Only the run-up to peak speed is used, so the
    deceleration after the finish line does not bend the fit. Returns dict(S0, tau, A0, t0, rmse).
    """
    from scipy.optimize import curve_fit

    t = np.asarray(t, dtype=float)
    s = np.asarray(s, dtype=float)
    nan = {"S0": np.nan, "tau": np.nan, "A0": np.nan, "t0": np.nan, "rmse": np.nan}
    if len(s) < 15 or np.nanmax(s) < 5:
        return nan
    peak = int(np.nanargmax(s))
    moving = np.flatnonzero(s[:peak + 1] > 0.3)
    if len(moving) == 0:
        return nan
    lo = max(moving[0] - 2, 0)
    tt, ss = t[lo:peak + 1] - t[lo], s[lo:peak + 1]
    if len(tt) < 10:
        return nan

    def model(x, S0, tau, t0):
        return np.where(x > t0, S0 * (1 - np.exp(-(x - t0) / tau)), 0.0)

    try:
        p, _ = curve_fit(model, tt, ss, p0=[ss.max(), 1.0, 0.1],
                         bounds=([3, 0.2, -1.0], [14, 3.0, 1.5]), maxfev=5000)
    except (RuntimeError, ValueError):
        return nan
    rmse = float(np.sqrt(np.mean((model(tt, *p) - ss) ** 2)))
    return {"S0": p[0], "tau": p[1], "A0": p[0] / p[1], "t0": p[2], "rmse": rmse}


def split_half(df, key, unit, value_fn, seed=0):
    """Split each key's units (e.g. games) randomly into halves and compute value_fn on each half.

    Returns a frame with one row per key and columns half_a, half_b. Used for reliability.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for k, d in df.groupby(key, sort=False):
        units = d[unit].unique()
        if len(units) < 4:
            continue
        rng.shuffle(units)
        half = set(units[: len(units) // 2])
        a = value_fn(d[d[unit].isin(half)])
        b = value_fn(d[~d[unit].isin(half)])
        rows.append({key: k, "half_a": a, "half_b": b})
    return pd.DataFrame(rows)


def spearman_brown(r):
    """Reliability of the full-length measure from a split-half correlation."""
    return 2 * r / (1 + r)


def eb_shrink(successes, trials, prior_mean=None, prior_n=None):
    """Beta-binomial empirical-Bayes shrinkage of rates (Efron & Morris 1975 style).

    prior_n (the pseudo-count) is estimated by the method of moments when not given.
    """
    x = np.asarray(successes, dtype=float)
    n = np.asarray(trials, dtype=float)
    p = x / np.where(n > 0, n, np.nan)
    m = prior_mean if prior_mean is not None else np.nansum(x) / np.nansum(n)
    if prior_n is None:
        w = n > 0
        var_obs = np.average((p[w] - m) ** 2, weights=n[w])
        var_binom = m * (1 - m) * np.mean(1 / n[w])
        var_true = max(var_obs - var_binom, 1e-6)
        prior_n = max(m * (1 - m) / var_true - 1, 1.0)
    return (x + m * prior_n) / (n + prior_n)


def utilization(s, acc, A0, S0):
    """Share of a player's own acceleration-speed capacity used at each frame.

    On the A-S line a = A0 (1 - v / S0), so a / A0 + v / S0 = 1 at full capacity whatever the speed:
    1.0 means the player is on his own limit line, 0.6 means 60% of it. Works at any speed, unlike
    a / a_max(v), which blows up near top speed.
    """
    return np.asarray(acc, dtype=float) / A0 + np.asarray(s, dtype=float) / S0
