"""Rhythm fingerprints for audio and MIDI — pattern/feel matching."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import mido
import numpy as np

from wav_io import load_audio_mono

GRID = 32  # 32nd-note grid over 2 bars (4/4)


def _onset_envelope(samples: np.ndarray, sr: int) -> np.ndarray:
    step = max(1, sr // 8000)
    x = samples[::step].astype(np.float64)
    eff_sr = sr / step
    diff = np.diff(x, prepend=x[0])
    env = np.abs(diff)
    k = max(1, int(eff_sr * 0.015))
    return np.convolve(env, np.ones(k) / k, mode="same"), eff_sr


def _pick_onsets(env: np.ndarray, sr: float, bpm: float, max_onsets: int = 64) -> np.ndarray:
    if bpm <= 0:
        bpm = 120.0
    beat_sec = 60.0 / bpm
    window = max(1, int(sr * 0.04))
    peaks: list[int] = []
    threshold = np.percentile(env, 75) * 0.5
    for i in range(window, len(env) - window):
        if env[i] < threshold:
            continue
        if env[i] >= env[i - window : i + window + 1].max():
            if not peaks or i - peaks[-1] > window // 2:
                peaks.append(i)
    if not peaks:
        return np.array([], dtype=np.float64)
    times = np.array(peaks, dtype=np.float64) / sr
    # Normalize to beat phase (0..2 bars)
    phases = (times % (beat_sec * 8)) / (beat_sec * 8)
    return phases[:max_onsets]


def rhythm_signature_from_audio(samples: np.ndarray, sr: int, bpm: float) -> np.ndarray:
    env, eff_sr = _onset_envelope(samples, sr)
    phases = _pick_onsets(env, eff_sr, bpm)
    sig = np.zeros(GRID, dtype=np.float32)
    if len(phases) == 0:
        return sig
    for p in phases:
        idx = int(p * GRID) % GRID
        sig[idx] += 1.0
    if sig.max() > 0:
        sig /= sig.max()
    return sig


def rhythm_signature_from_midi(path: Path, bpm_hint: float = 120.0) -> np.ndarray:
    sig = np.zeros(GRID, dtype=np.float32)
    try:
        midi = mido.MidiFile(str(path))
    except (OSError, mido.MidiFileError):
        return sig

    tempo = 500000
    events: list[float] = []
    for track in midi.tracks:
        tick = 0
        track_tempo = tempo
        for msg in track:
            tick += msg.time
            if msg.type == "set_tempo":
                track_tempo = msg.tempo
            if msg.type == "note_on" and msg.velocity > 0:
                sec = mido.tick2second(tick, midi.ticks_per_beat, track_tempo)
                events.append(sec)

    if not events:
        return sig

    if bpm_hint <= 0:
        bpm_hint = 120.0
    beat = 60.0 / bpm_hint
    bar_len = beat * 4
    span = bar_len * 2
    for t in events[:128]:
        phase = (t % span) / span
        idx = int(phase * GRID) % GRID
        sig[idx] += 1.0
    if sig.max() > 0:
        sig /= sig.max()
    return sig


@lru_cache(maxsize=4096)
def fingerprint_file(path_str: str, kind: str, bpm_hint: float) -> tuple[float, ...]:
    path = Path(path_str)
    if kind == "mid":
        sig = rhythm_signature_from_midi(path, bpm_hint)
    else:
        try:
            samples, sr = load_audio_mono(path)
            sig = rhythm_signature_from_audio(samples, sr, bpm_hint)
        except (OSError, ValueError):
            sig = np.zeros(GRID, dtype=np.float32)
    return tuple(float(x) for x in sig)


def rhythm_similarity(sig_a: np.ndarray, sig_b: np.ndarray) -> float:
    if sig_a.shape != sig_b.shape:
        return 0.0
    na = np.linalg.norm(sig_a)
    nb = np.linalg.norm(sig_b)
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    return float(np.dot(sig_a, sig_b) / (na * nb))
