"""Original background music for each video, made on the spot: free, and nobody else owns it.

A short loop in a playful style: plucked-string chords (Karplus-Strong), a bouncy bass, light drums
and a catchy melody that repeats with small changes. Tempo, key, chords and melody come from a
seed, so each video gets its own tune and the same video always gets the same one.
"""

import wave

import numpy as np

RATE = 44100
# Semitones above the key's root for each chord; four bars, one chord per bar.
PROGRESSIONS = [
    [(0, 4, 7), (7, 11, 14), (9, 12, 16), (5, 9, 12)],  # I  V  vi IV
    [(0, 4, 7), (9, 12, 16), (5, 9, 12), (7, 11, 14)],  # I  vi IV V
    [(0, 4, 7), (5, 9, 12), (0, 4, 7), (7, 11, 14)],  # I  IV I  V
    [(5, 9, 12), (7, 11, 14), (4, 7, 11), (9, 12, 16)],  # IV V  iii vi
]
PENTATONIC = [0, 2, 4, 7, 9, 12, 14, 16]
KEYS = [196.00, 220.00, 233.08, 261.63, 293.66]  # G3 A3 Bb3 C4 D4


def make_track(path, seconds, seed=0):
    """Write a stereo 16-bit WAV of at least `seconds` seconds to path."""
    rng = np.random.default_rng(seed)
    bpm = int(rng.integers(100, 126))
    root = KEYS[int(rng.integers(len(KEYS)))]
    chords = PROGRESSIONS[int(rng.integers(len(PROGRESSIONS)))]
    beat = 60 / bpm
    bar = 4 * beat
    total = int((seconds + 1) * RATE)
    left, right = np.zeros(total), np.zeros(total)

    motif = _motif(rng)
    n_bars = int(np.ceil((seconds + 1) / bar))
    for b in range(n_bars):
        start = b * bar
        chord = chords[b % len(chords)]
        # Strummed arpeggio in eighths: root, third, fifth, third... panned slightly left.
        for step in range(8):
            note = chord[[0, 1, 2, 1][step % 4]] + (12 if step in (2, 6) else 0)
            _add(left, right, _pluck(_freq(root, note), beat * 1.5, rng), start + step * beat / 2, 0.30, pan=-0.3)
        # Bass on every beat, octave below, bouncing to the fifth on beat 3.
        for k in range(4):
            note = chord[0] - 12 + (7 if k == 2 else 0)
            _add(left, right, _bass(_freq(root, note), beat * 0.9), start + k * beat, 0.45, pan=0.0)
        # Drums: soft kick on 1 and 3, snap on 2 and 4, shaker on the offbeats.
        for k in range(4):
            if k in (0, 2):
                _add(left, right, _kick(), start + k * beat, 0.55, pan=0.0)
            else:
                _add(left, right, _snap(rng), start + k * beat, 0.18, pan=0.1)
            _add(left, right, _shaker(rng), start + (k + 0.5) * beat, 0.035, pan=0.4)
        # Melody: the motif over the chord, a little different every other bar.
        for slot, step in enumerate(motif):
            if step is None:
                continue
            if b % 2 and slot == len(motif) - 1:
                step = (step + 2) % len(PENTATONIC)  # answer the phrase instead of repeating it
            note = PENTATONIC[step] + 12
            _add(left, right, _lead(_freq(root, note), beat * 0.45), start + slot * beat / 2, 0.22, pan=0.25)

    mix = np.stack([left, right], axis=1)[: int(seconds * RATE) + RATE // 2]
    mix = np.tanh(mix * 1.2)  # gentle limiter
    mix *= 0.89 / max(np.abs(mix).max(), 1e-9)  # about -1 dBFS
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes((mix * 32767).astype("<i2").tobytes())
    return path


def _motif(rng):
    """Eight eighth-note slots of a pentatonic tune, with rests so it breathes."""
    steps, step = [], int(rng.integers(2, 5))
    for slot in range(8):
        if rng.random() < 0.3 and slot not in (0, 4):
            steps.append(None)
            continue
        step = int(np.clip(step + rng.choice([-2, -1, 1, 1, 2]), 0, len(PENTATONIC) - 1))
        steps.append(step)
    return steps


def _freq(root, semitones):
    return root * 2 ** (semitones / 12)


def _add(left, right, sound, at, gain, pan):
    i = int(at * RATE)
    if i >= len(left):
        return
    sound = sound[: len(left) - i] * gain
    left[i : i + len(sound)] += sound * (1 - pan) / 2 * 2 ** 0.5
    right[i : i + len(sound)] += sound * (1 + pan) / 2 * 2 ** 0.5


def _pluck(freq, length, rng):
    """Karplus-Strong plucked string, computed one period at a time (fast in numpy)."""
    period = max(2, int(RATE / freq))
    n = int(length * RATE)
    out = np.zeros(n + period)
    burst = rng.uniform(-1, 1, period + 2)
    out[:period] = (burst[:-2] + burst[1:-1] + burst[2:]) / 3  # a softer pick: less "click", more "pluck"
    for start in range(period, n + period, period):
        prev = out[start - period : start]
        shifted = np.concatenate(([out[start - period - 1] if start > period else 0.0], prev[:-1]))
        block = 0.996 * 0.5 * (prev + shifted)
        out[start : start + period] = block[: len(out) - start]
    return out[period : n + period] * np.linspace(1, 0.2, n)


def _bass(freq, length):
    t = np.arange(int(length * RATE)) / RATE
    tone = np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(4 * np.pi * freq * t)
    return tone * np.exp(-t * 4) * np.minimum(1, t * 200)


def _lead(freq, length):
    """A soft marimba-like note: two sines with a quick decay and a hint of vibrato."""
    t = np.arange(int(length * RATE)) / RATE
    vibrato = 1 + 0.004 * np.sin(2 * np.pi * 5.5 * t)
    tone = np.sin(2 * np.pi * freq * vibrato * t) + 0.25 * np.sin(2 * np.pi * 4 * freq * t)
    return tone * np.exp(-t * 7) * np.minimum(1, t * 300)


def _kick():
    t = np.arange(int(0.25 * RATE)) / RATE
    pitch = 50 + 90 * np.exp(-t * 30)
    return np.sin(2 * np.pi * np.cumsum(pitch) / RATE) * np.exp(-t * 14)


def _snap(rng):
    t = np.arange(int(0.12 * RATE)) / RATE
    noise = rng.uniform(-1, 1, len(t))
    return np.diff(noise, prepend=0) * np.exp(-t * 35)  # differenced noise: brighter, like a clap


def _shaker(rng):
    t = np.arange(int(0.06 * RATE)) / RATE
    return np.diff(rng.uniform(-1, 1, len(t)), prepend=0) * np.exp(-t * 60)
