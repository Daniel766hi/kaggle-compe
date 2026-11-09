"""Tests for the live camera lab, on synthetic video (no camera needed)."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")
spec = importlib.util.spec_from_file_location("vision_lab", Path(__file__).parents[1] / "camera_lab" / "vision_lab.py")
vl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vl)


def frames(n_objects=4, direction=1, size=(240, 320)):
    """A static textured background with n coloured discs moving across the middle line, one after another."""
    h, w = size
    rng = np.random.default_rng(0)
    bg = (rng.integers(60, 90, (h, w, 3))).astype(np.uint8)
    out = []
    for f in range(30):  # let the background model settle
        out.append(bg.copy())
    for k in range(n_objects):
        x = 40 + (k * 70) % (w - 80)
        for step in range(45):
            img = bg.copy()
            y = 10 + step * 5 if direction > 0 else h - 10 - step * 5
            cv2.circle(img, (x, y), 18, (40, 60, 230), -1)
            out.append(img)
        out.extend(bg.copy() for _ in range(8))
    return out


def test_counter_counts_each_object_crossing_once():
    counter = vl.LineCounter()
    for img in frames(4, direction=1):
        counter.update(img)
    assert (counter.down, counter.up) == (4, 0)


def test_counter_knows_the_direction():
    counter = vl.LineCounter()
    for img in frames(3, direction=-1):
        counter.update(img)
    assert (counter.down, counter.up) == (0, 3)


def test_every_mode_returns_a_frame_of_the_same_size():
    lab = vl.Lab()
    lab.detector = type("Stub", (), {"kind": "faces", "__call__": lambda self, f: [("face", 1.0, (10, 10, 40, 40))]})()
    clip = frames(1)[:40]
    for mode in vl.MODES:
        lab.mode = mode
        for img in clip:
            out = lab.process(img)
        assert out.shape == img.shape, mode
    lab.mode = "colour"
    lab.on_click(vl.cv2.EVENT_LBUTTONDOWN, 40, 20 + 5 * 5)
    assert lab.pick_hsv is not None
