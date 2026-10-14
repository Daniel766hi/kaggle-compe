"""Masses: molecular formula -> monoisotopic neutral mass, and precursor m/z -> neutral mass."""

import re

import numpy as np

ELECTRON = 0.000548579909
PROTON = 1.007276466812
H2O = 18.010564684

MONO = {
    "H": 1.00782503207, "D": 2.0141017778, "C": 12.0, "N": 14.0030740048, "O": 15.99491461956,
    "F": 18.99840322, "Na": 22.9897692809, "Mg": 23.985041700, "Si": 27.9769265325,
    "P": 30.97376163, "S": 31.97207100, "Cl": 34.96885268, "K": 38.96370668, "Ca": 39.96259098,
    "Fe": 55.9349375, "Co": 58.9331950, "Ni": 57.9353429, "Cu": 62.9295975, "Zn": 63.9291422,
    "As": 74.9215965, "Se": 79.9165213, "Br": 78.9183371, "B": 11.0093054, "I": 126.904473,
    "Sn": 119.9021947, "Hg": 201.970643, "Pt": 194.9647911, "Al": 26.98153863, "Li": 7.01600455,
    "Mn": 54.9380451, "Cr": 51.9405075, "Ti": 47.9479463, "Ag": 106.905097, "Au": 196.9665687,
    "Gd": 157.9241039, "Sb": 120.9038157, "Bi": 208.9803987, "Ge": 73.9211778, "Te": 129.9062244,
    "W": 183.9509312, "Mo": 97.9054082, "V": 50.9439595, "Ba": 137.9052472, "Sr": 87.9056121,
    "Cs": 132.905451933, "Rb": 84.911789738, "Tl": 204.9744275, "Pb": 207.9766521,
}

# neutral M = (m/z - add) / mult for singly charged adducts in the test set (plus a few common ones).
ADDUCTS = {
    "[M+H]+": (1, PROTON),
    "[M+NH4]+": (1, 18.033825567),
    "[M-H2O+H]+": (1, PROTON - H2O),
    "[M-2H2O+H]+": (1, PROTON - 2 * H2O),
    "[M+Na]+": (1, 22.9897692809 - ELECTRON),
    "[M+K]+": (1, 38.96370668 - ELECTRON),
    "[M]+": (1, -ELECTRON),
    "[M-H]-": (1, -PROTON),
    "[M-H2O-H]-": (1, -PROTON - H2O),
    "[M+CH2O2-H]-": (1, 46.005479303 - PROTON),
    "[M+C2H4O2-H]-": (1, 60.021129367 - PROTON),
    "[M+Cl]-": (1, 34.96885268 + ELECTRON),
    "[2M+H]+": (2, PROTON),
    "[2M+Na]+": (2, 22.9897692809 - ELECTRON),
    "[2M-H]-": (2, -PROTON),
}

_TOKEN = re.compile(r"([A-Z][a-z]?)(\d*)")


def formula_mass(formula):
    """Monoisotopic mass of a neutral formula like 'C20H15N3O2'; NaN if it can't be parsed."""
    if not isinstance(formula, str) or not formula:
        return float("nan")
    f = formula.strip()
    if not re.fullmatch(r"(?:[A-Z][a-z]?\d*)+", f):
        return float("nan")
    total = 0.0
    for el, n in _TOKEN.findall(f):
        if el not in MONO:
            return float("nan")
        total += MONO[el] * (int(n) if n else 1)
    return total


def neutral_mass(precursor_mz, adduct):
    """Neutral monoisotopic mass implied by a precursor m/z and adduct; NaN for unknown adducts."""
    mult, add = ADDUCTS.get(adduct, (None, None))
    if mult is None:
        return float("nan")
    return (float(precursor_mz) - add) / mult


def ppm(a, b):
    return (np.asarray(a) - np.asarray(b)) / np.asarray(b) * 1e6
