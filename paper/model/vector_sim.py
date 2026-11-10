"""Vectorized simulation: many scenarios in one Euler integration.

PySD integrates one scenario at a time and spends most of each step in Python overhead.
Here the PySD translation (mbg_poultry.py) is copied to mbg_poultry_vec.py with scalar-only
helpers replaced by element-wise numpy versions, every parameter is passed as an array with
one entry per scenario, and the stateful elements are stepped together with the same Euler
update PySD uses. `check_equivalence` compares the result with ordinary PySD runs; the
ensemble scripts call it before use.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from common import HERE, RETURN_COLS, calibrated, load_model, model_time_step

VEC_FILE = HERE / "mbg_poultry_vec.py"

_HEADER = '''
# ---- element-wise replacements inserted by vector_sim.py ----
_SMALL_VENSIM = 1e-6


def _vf(x):
    return x


def if_then_else(condition, val_if_true, val_if_false):
    c = np.asarray(condition)
    if c.ndim == 0:
        return val_if_true() if bool(c) else val_if_false()
    with np.errstate(all="ignore"):
        return np.where(c, val_if_true(), val_if_false())


def pulse(time, start, repeat_time=0, width=None, magnitude=None, end=None):
    assert repeat_time == 0 and end is None, "vector pulse supports single pulses only"
    t = time()
    width = .5 * time.time_step() if width is None else width
    out = magnitude / time.time_step() if magnitude is not None else 1
    inside = (np.asarray(start) - _SMALL_VENSIM <= t) & (t < np.asarray(start) + width)
    return np.where(inside, out, 0) if np.ndim(inside) else (out if inside else 0)


def zidz(numerator, denominator):
    d = np.asarray(denominator)
    with np.errstate(all="ignore"):
        r = np.where(np.abs(d) < _SMALL_VENSIM, 0, numerator / np.where(d == 0, 1, d))
    return r if np.ndim(r) else float(r)
# ---- end of replacements ----
'''


def _write_vector_module():
    load_model()                      # makes sure mbg_poultry.py is translated from the current .mdl
    src = (HERE / "mbg_poultry.py").read_text()
    src = re.sub(r"\bfloat\(", "_vf(", src)
    m = re.search(r"^from pysd\.py_backend\.functions import (.+)\n", src, flags=re.M)
    names = {x.strip() for x in m.group(1).split(",")}
    assert names <= {"pulse", "if_then_else", "zidz"}, f"no vector version of {names}"
    src = src[:m.start()] + src[m.end():]
    imports_end = src.index("from pysd import Component")
    line_end = src.index("\n", imports_end) + 1
    src = src[:line_end] + _HEADER + src[line_end:]
    VEC_FILE.write_text(src)


_VMODEL = None


def _vector_model():
    global _VMODEL
    if _VMODEL is None:
        import pysd
        _write_vector_module()
        _VMODEL = pysd.load(str(VEC_FILE))
    return _VMODEL


def run_batch(param_list: list[dict], time_step: float | None = None,
              columns: list[str] | None = None, use_calibrated: bool = True) -> dict[str, np.ndarray]:
    """Simulate len(param_list) scenarios together. Returns {column: array (313 weeks, n)}."""
    columns = columns or RETURN_COLS
    n = len(param_list)
    m = _vector_model()
    m.reload()
    base = dict(calibrated()) if use_calibrated else {}
    keys = sorted(set(base) | {k for p in param_list for k in p})
    params = {}
    scalar = load_model()
    for k in keys:
        default = base.get(k)
        if default is None:      # value written in the .mdl, for scenarios that do not set it
            default = float(getattr(scalar.components, scalar._namespace[k])())
        vals = np.array([p.get(k, default) for p in param_list], dtype=float)
        params[k] = (lambda v=vals: v)
    dt = time_step or model_time_step()
    m._config_simulation(params, columns, np.arange(0, 313, 1.0), "original", None, dt, None, True, progress=False)
    py = [m._namespace[c] for c in columns]
    funcs = [getattr(m.components, p) for p in py]
    out = {c: [] for c in columns}
    stateful = m._dynamicstateful_elements
    for s in stateful:                # give every state one entry per scenario
        st = np.asarray(s.state, dtype=float)
        if getattr(s, "order", None) is not None:          # SMOOTH / DELAY: (order,) -> (order, n)
            st = np.repeat(st[:, None], n, axis=1) if st.ndim == 1 else st
            assert st.shape == (s.order, n), (s.py_name, st.shape)
        else:                                               # INTEG: () -> (n,)
            st = np.broadcast_to(st, (n,)).copy()
        s.state = st

    def record():
        for c, f in zip(columns, funcs):
            out[c].append(np.broadcast_to(np.asarray(f(), dtype=float), (n,)).copy())

    with np.errstate(all="ignore"):
        while m.time.in_bounds():
            if m.time.in_return():
                record()
            ddts = [s.ddt() for s in stateful]
            for s, d in zip(stateful, ddts):
                s.update(s.state + d * dt)
            m.time.update(m.time() + dt)
            m.clean_caches()
        if m.time.in_return():
            record()
    return {c: np.vstack(v) for c, v in out.items()}


def frames(batch: dict[str, np.ndarray]) -> list[pd.DataFrame]:
    """Split a batch into one DataFrame per scenario (index = week), like common.run()."""
    cols = list(batch)
    arr = np.stack([batch[c] for c in cols], axis=2)        # weeks x scenarios x columns
    idx = pd.Index(np.arange(arr.shape[0], dtype=float), name="time")
    return [pd.DataFrame(arr[:, j, :], index=idx, columns=cols) for j in range(arr.shape[1])]


def check_equivalence(param_list: list[dict], time_step: float | None = None,
                      columns: list[str] | None = None, tol: float = 1e-9) -> float:
    """Max relative difference between run_batch and ordinary PySD runs; raises if above tol."""
    from common import run
    columns = columns or RETURN_COLS
    vec = frames(run_batch(param_list, time_step, columns))
    worst = 0.0
    for p, v in zip(param_list, vec):
        s = run(p, time_step=time_step, columns=columns)[columns]
        scale = np.maximum(1.0, s.abs().max())
        worst = max(worst, float(((v.values - s.values) / scale.values).__abs__().max()))
    if worst > tol:
        raise AssertionError(f"vectorized run differs from PySD by {worst:.3g} (tolerance {tol:g})")
    return worst
