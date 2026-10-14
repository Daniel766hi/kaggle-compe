"""Mass arithmetic used by the Enveda CASMI 2026 search."""

import math

import pytest

from enveda_casmi26.chem import formula_mass, neutral_mass, ppm

CAFFEINE = 194.080375741  # C8H10N4O2


def test_formula_mass():
    assert formula_mass("C8H10N4O2") == pytest.approx(CAFFEINE, abs=1e-6)
    assert formula_mass("CH4") == pytest.approx(16.0313, abs=1e-4)
    assert math.isnan(formula_mass("C8H10N4O2+")) and math.isnan(formula_mass(None))
    assert math.isnan(formula_mass("C2Xx3"))


@pytest.mark.parametrize("adduct, mz", [
    ("[M+H]+", 195.087652), ("[M-H]-", 193.073099), ("[M+Na]+", 217.069596),
    ("[M+NH4]+", 212.114201), ("[M+CH2O2-H]-", 239.078578), ("[M+Cl]-", 229.049777),
])
def test_neutral_mass_roundtrip(adduct, mz):
    assert abs(ppm(neutral_mass(mz, adduct), CAFFEINE)) < 2


def test_unknown_adduct():
    assert math.isnan(neutral_mass(100.0, "[M+Xe]+"))


def test_cosine_identical_and_disjoint():
    import numpy as np

    from enveda_casmi26.library import prepare_peaks
    from enveda_casmi26.search import cosine

    m, i = prepare_peaks([50.0, 80.0, 120.0], [1.0, 0.5, 0.25])
    assert cosine(m, i, m, i, 0.01) == pytest.approx(1.0, abs=1e-6)
    m2, i2 = prepare_peaks([51.0, 81.0], [1.0, 1.0])
    assert cosine(m, i, m2, i2, 0.01) == 0.0
    m3, i3 = prepare_peaks([50.004, 200.0], [1.0, 1.0])
    assert 0 < cosine(m, i, m3, i3, 0.01) < 1
    # top-k keeps the most intense peaks, sorted by m/z
    mk, _ = prepare_peaks(np.arange(100.0), np.arange(1.0, 101.0), top_k=5)
    assert list(mk) == [95.0, 96.0, 97.0, 98.0, 99.0]
