import numpy as np
import pandas as pd
import pytest

from nfl_bdb2027.movement import (BIN, binned_extremes, eb_shrink, fit_as_profile, fit_sprint,
                                  robust_envelope, signed_accel, spearman_brown,
                                  utilization)


def sprint_trace(S0=10.0, tau=1.2, n=60):
    t = np.arange(n) * 0.1
    return t, S0 * (1 - np.exp(-t / tau))


def test_fit_sprint_recovers_parameters():
    t, s = sprint_trace()
    s = np.r_[np.zeros(5), s, s[-1] - np.arange(1, 11) * 0.5]  # standing start, then slow down
    t = np.arange(len(s)) * 0.1
    fit = fit_sprint(t, s)
    assert fit["S0"] == pytest.approx(10.0, rel=0.02)
    assert fit["tau"] == pytest.approx(1.2, rel=0.05)
    assert fit["A0"] == pytest.approx(10.0 / 1.2, rel=0.06)


def test_fit_sprint_rejects_walk():
    t = np.arange(40) * 0.1
    assert np.isnan(fit_sprint(t, np.full(40, 2.0))["S0"])


def test_signed_accel_keeps_sign_and_respects_groups():
    frames = pd.DataFrame({
        "k": [1] * 5 + [2] * 5,
        "t": np.r_[np.arange(5) * 0.1, np.arange(5) * 0.1],
        "s": [0, 1, 2, 3, 4, 4, 3, 2, 1, 0],
    })
    _, acc = signed_accel(frames, ["k"])
    assert np.isnan(acc[0]) and np.isnan(acc[5])  # first frame of each sequence
    assert acc[2] == pytest.approx(10.0)
    assert acc[7] == pytest.approx(-10.0)


def test_signed_accel_masks_time_gaps():
    frames = pd.DataFrame({"k": [1] * 4, "t": [0.0, 0.1, 0.5, 0.6], "s": [1.0, 2, 3, 4]})
    _, acc = signed_accel(frames, ["k"])
    assert np.isnan(acc[2]) and not np.isnan(acc[3])


def test_as_profile_matches_sprint_line():
    # every point of a mono-exponential sprint lies on a = A0 (1 - v / S0)
    S0, tau = 10.0, 1.25
    v = np.linspace(0.2, 9.8, 200)
    a = (S0 - v) / tau
    df = pd.DataFrame({"p": 1, "s_smooth": v, "acc": a})
    env = binned_extremes(df, ["p"])
    fit = fit_as_profile(env["bin"], env["acc_max"])
    # bin centres are up to BIN/2 off the true speed, so allow a small tolerance
    assert fit["S0"] == pytest.approx(S0, abs=BIN)
    assert fit["A0"] == pytest.approx(S0 / tau, rel=0.05)
    assert fit["r2"] > 0.99


def test_as_profile_needs_enough_points():
    assert np.isnan(fit_as_profile([20, 21], [2.0, 1.0])["A0"])


def test_robust_envelope_ignores_single_glitch():
    per_game = pd.DataFrame({"p": 1, "game": [1, 2, 3], "bin": 10, "acc_max": [9.0, 3.0, 2.5]},
                            index=[0, 0, 1])  # duplicate index, as after concatenating seasons
    env = robust_envelope(per_game, ["p"], k=2)
    assert env["acc_max"].item() == 3.0


def test_spearman_brown_and_shrinkage():
    assert spearman_brown(0.5) == pytest.approx(2 / 3)
    shrunk = eb_shrink([0, 10, 1], [1, 100, 10], prior_mean=0.1, prior_n=10)
    assert shrunk[0] == pytest.approx(1 / 11)
    assert shrunk[1] == pytest.approx(0.1)


def test_as_profile_rejects_flat_or_noisy_envelope():
    bins = np.arange(12, 40)
    rng = np.random.default_rng(0)
    assert np.isnan(fit_as_profile(bins, 3 + rng.normal(0, 1, bins.size))["S0"])  # no real slope
    assert np.isnan(fit_as_profile(bins, 6 - 0.01 * bins)["S0"])  # S0 far beyond human speed


def test_utilization_is_one_on_the_capacity_line():
    A0, S0 = 8.0, 10.0
    v = np.array([0.0, 5.0, 9.0])
    on_line = A0 * (1 - v / S0)
    assert np.allclose(utilization(v, on_line, A0, S0), 1.0)
    assert utilization(5.0, 0.0, A0, S0) == pytest.approx(0.5)  # cruising at half top speed
