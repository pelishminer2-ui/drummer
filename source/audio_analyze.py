"""Analyze guitar (or any) audio — tempo, rhythm, key, and deep features."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from gpu_backend import (
    get_gpu_info,
    gpu_chroma,
    gpu_deep_embedding,
    gpu_mfcc,
    project_embedding,
)
from rhythm_fingerprint import rhythm_signature_from_audio
from wav_io import load_audio_mono, write_wav_mono

DEFAULT_COUNT_IN_SEC = 5.0
_RECORD_SAMPLE_RATE = 44100


def _metronome_click(
    sample_rate: int = _RECORD_SAMPLE_RATE,
    *,
    accent: bool = False,
    duration_ms: float = 22.0,
) -> np.ndarray:
    """Built-in metronome tick for record count-in (always used)."""
    n = max(1, int(sample_rate * duration_ms / 1000.0))
    t = np.linspace(0.0, duration_ms / 1000.0, n, dtype=np.float32)
    freq = 1400.0 if accent else 1000.0
    tick = np.sin(2.0 * np.pi * freq * t) * np.exp(-t * (75.0 if accent else 95.0))
    level = 1.0 if accent else 0.85
    return np.clip(tick * level, -1.0, 1.0).astype(np.float32)


def build_count_in_track(
    seconds: float = DEFAULT_COUNT_IN_SEC,
    sample_rate: int = _RECORD_SAMPLE_RATE,
) -> np.ndarray:
    """One built-in metronome click per second, prepended to recordings."""
    total = int(max(0.0, seconds) * sample_rate)
    if total == 0:
        return np.zeros(0, dtype=np.float32)
    out = np.zeros(total, dtype=np.float32)
    for beat in range(int(seconds)):
        click = _metronome_click(sample_rate, accent=(beat == 0))
        start = beat * sample_rate
        end = min(start + len(click), total)
        out[start:end] += click[: end - start]
    return out


def play_count_in(
    seconds: float = DEFAULT_COUNT_IN_SEC,
    sample_rate: int = _RECORD_SAMPLE_RATE,
    on_tick: Callable[[int], None] | None = None,
) -> None:
    """Audible built-in metronome count-in — one tick per second, then record."""
    from audio_prep import ensure_pygame_mixer, mono_to_pygame_sound

    ensure_pygame_mixer(sample_rate)
    beats = max(0, int(seconds))
    for beat in range(beats):
        remaining = beats - beat
        if on_tick:
            on_tick(remaining)
        click = _metronome_click(sample_rate, accent=(beat == 0))
        sound = mono_to_pygame_sound(click, sample_rate)
        channel = sound.play()
        if channel is None:
            raise RuntimeError("Metronome click could not play — check Windows volume and output device.")
        click_dur = len(click) / sample_rate
        end = time.monotonic() + click_dur + 0.05
        while channel.get_busy() and time.monotonic() < end:
            time.sleep(0.005)
        pad = 1.0 - click_dur
        if pad > 0 and beat < beats - 1:
            time.sleep(pad)


def record_guitar(
    path: Path,
    duration_sec: float = 8.0,
    sample_rate: int = _RECORD_SAMPLE_RATE,
    *,
    count_in_sec: float = DEFAULT_COUNT_IN_SEC,
    on_count_in_tick: Callable[[int], None] | None = None,
    on_recording_start: Callable[[], None] | None = None,
) -> Path:
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise RuntimeError("Recording requires: pip install sounddevice") from exc

    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    play_count_in(count_in_sec, sample_rate, on_tick=on_count_in_tick)

    if on_recording_start:
        on_recording_start()

    frames = int(duration_sec * sample_rate)
    recording = sd.rec(frames, samplerate=sample_rate, channels=1, dtype="float32")
    sd.wait()
    mono = recording.flatten().astype(np.float32)

    count_in = build_count_in_track(count_in_sec, sample_rate)
    if len(count_in):
        full = np.concatenate([count_in, mono])
    else:
        full = mono

    write_wav_mono(path, full, sample_rate)
    return path


@dataclass
class AudioAnalysis:
    path: Path
    bpm: float
    bpm_confidence: float
    duration_sec: float
    sample_rate: int
    rhythm_signature: np.ndarray = field(default_factory=lambda: np.zeros(32, dtype=np.float32))
    key_root: str = "?"
    key_mode: str = "?"
    key_confidence: float = 0.0
    chroma_vector: np.ndarray = field(default_factory=lambda: np.zeros(12, dtype=np.float32))
    mfcc_profile: np.ndarray = field(default_factory=lambda: np.zeros(13, dtype=np.float32))
    deep_embedding: np.ndarray = field(default_factory=lambda: np.zeros(128, dtype=np.float32))
    gpu_backend: str = "CPU"
    energy: float = 0.0
    brightness: float = 0.0


# Krumhansl-Kessler major / minor profiles
_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _load_wav_mono(path: Path) -> tuple[np.ndarray, int]:
    from wav_io import load_audio_mono

    return load_audio_mono(path)


def _estimate_bpm(samples: np.ndarray, sr: int) -> tuple[float, float]:
    if len(samples) < sr:
        return 120.0, 0.0

    step = max(1, sr // 4000)
    x = samples[::step].astype(np.float64)
    eff_sr = sr / step

    diff = np.diff(x, prepend=x[0])
    env = np.abs(diff)
    kernel = max(1, int(eff_sr * 0.02))
    env = np.convolve(env, np.ones(kernel) / kernel, mode="same")

    min_bpm, max_bpm = 60.0, 200.0
    min_lag = int(eff_sr * 60.0 / max_bpm)
    max_lag = int(eff_sr * 60.0 / min_bpm)
    max_lag = min(max_lag, len(env) // 2)
    if max_lag <= min_lag:
        return 120.0, 0.0

    segment = env[: max_lag * 2]
    segment = segment - segment.mean()
    if np.max(np.abs(segment)) < 1e-9:
        return 120.0, 0.0

    best_lag = min_lag
    best_corr = -1.0
    for lag in range(min_lag, max_lag + 1):
        a = segment[:-lag]
        b = segment[lag:]
        denom = np.linalg.norm(a) * np.linalg.norm(b)
        if denom < 1e-9:
            continue
        corr = float(np.dot(a, b) / denom)
        if corr > best_corr:
            best_corr = corr
            best_lag = lag

    bpm = 60.0 * eff_sr / best_lag
    confidence = max(0.0, min(1.0, best_corr))
    return round(bpm, 1), confidence


def _chroma_from_fft(samples: np.ndarray, sr: int) -> np.ndarray:
    """12-bin chroma via STFT energy (librosa-quality fallback)."""
    n_fft = 4096
    hop = n_fft // 4
    chroma = np.zeros(12, dtype=np.float64)
    if len(samples) < n_fft:
        return chroma.astype(np.float32)

    use = samples[: min(len(samples), sr * 30)]
    for start in range(0, len(use) - n_fft, hop):
        frame = use[start : start + n_fft] * np.hanning(n_fft)
        spec = np.abs(np.fft.rfft(frame))
        freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
        for i, f in enumerate(freqs[1:], 1):
            if f < 50 or f > 2000:
                continue
            midi = 69 + 12 * np.log2(f / 440.0)
            pc = int(round(midi)) % 12
            chroma[pc] += spec[i] ** 2

    if chroma.max() > 0:
        chroma /= chroma.max()
    return chroma.astype(np.float32)


def _estimate_key(chroma: np.ndarray) -> tuple[str, str, float]:
    if chroma.sum() < 1e-6:
        return "?", "?", 0.0
    best_score = -1.0
    best_root = 0
    best_mode = "major"
    for shift in range(12):
        rolled = np.roll(chroma, -shift)
        maj = float(np.corrcoef(rolled, _MAJOR)[0, 1])
        min_ = float(np.corrcoef(rolled, _MINOR)[0, 1])
        if not np.isfinite(maj):
            maj = 0.0
        if not np.isfinite(min_):
            min_ = 0.0
        if maj > best_score:
            best_score = maj
            best_root = shift
            best_mode = "major"
        if min_ > best_score:
            best_score = min_
            best_root = shift
            best_mode = "minor"
    conf = max(0.0, min(1.0, best_score))
    return _NOTE_NAMES[best_root], best_mode, conf


def _mfcc_profile(samples: np.ndarray, sr: int) -> np.ndarray:
    """Deep timbre profile — GPU, librosa, or spectral fallback."""
    gpu_result = gpu_mfcc(samples, sr)
    if gpu_result is not None:
        return gpu_result

    try:
        import librosa

        y = samples.astype(np.float32)
        if len(y) > sr * 45:
            y = y[: sr * 45]
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
        return mfcc.mean(axis=1).astype(np.float32)
    except ImportError:
        pass

    n_fft = 2048
    if len(samples) < n_fft:
        return np.zeros(13, dtype=np.float32)
    frame = samples[:n_fft] * np.hanning(n_fft)
    spec = np.abs(np.fft.rfft(frame)) + 1e-9
    bands = np.array_split(spec, 13)
    profile = np.array([np.log1p(b.mean()) for b in bands], dtype=np.float32)
    profile -= profile.mean()
    return profile


def _deep_embedding(samples: np.ndarray, sr: int) -> np.ndarray:
    """AI-ready embedding for groove similarity and future generation."""
    gpu_emb = gpu_deep_embedding(samples, sr)
    if gpu_emb is not None:
        return project_embedding(gpu_emb)

    mfcc = _mfcc_profile(samples, sr)
    if mfcc.shape[0] >= 13:
        padded = np.zeros(128, dtype=np.float32)
        padded[:13] = mfcc
        norm = np.linalg.norm(padded)
        if norm > 1e-9:
            padded /= norm
        return project_embedding(padded)
    return np.zeros(128, dtype=np.float32)


def _spectral_brightness(samples: np.ndarray, sr: int) -> float:
    n = min(len(samples), sr * 10)
    if n < 512:
        return 0.5
    spec = np.abs(np.fft.rfft(samples[:512] * np.hanning(512)))
    freqs = np.fft.rfftfreq(512, 1.0 / sr)
    total = spec.sum() + 1e-9
    high = spec[freqs > 2000].sum()
    return float(high / total)


def analyze_file(path: Path, *, trim_leading_sec: float = 0.0) -> AudioAnalysis:
    path = path.resolve()
    samples, sr = _load_wav_mono(path)
    if trim_leading_sec > 0:
        skip = int(trim_leading_sec * sr)
        if skip < len(samples) - sr * 2:
            samples = samples[skip:]
    bpm, confidence = _estimate_bpm(samples, sr)
    duration = len(samples) / sr

    chroma = gpu_chroma(samples, sr)
    if chroma is None:
        chroma = _chroma_from_fft(samples, sr)
    root, mode, key_conf = _estimate_key(chroma)
    rhythm = rhythm_signature_from_audio(samples, sr, bpm)
    mfcc = _mfcc_profile(samples, sr)
    embedding = _deep_embedding(samples, sr)
    energy = float(np.sqrt(np.mean(samples**2)))
    brightness = _spectral_brightness(samples, sr)
    gpu_label = get_gpu_info().label

    return AudioAnalysis(
        path=path,
        bpm=bpm,
        bpm_confidence=confidence,
        duration_sec=duration,
        sample_rate=sr,
        rhythm_signature=rhythm,
        key_root=root,
        key_mode=mode,
        key_confidence=key_conf,
        chroma_vector=chroma,
        mfcc_profile=mfcc,
        deep_embedding=embedding,
        gpu_backend=gpu_label,
        energy=energy,
        brightness=brightness,
    )
