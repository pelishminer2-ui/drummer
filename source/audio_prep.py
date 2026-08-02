"""Shared audio prep — declick, resample, mixer init (used by grooves + kit clicks)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pygame
import pygame.sndarray

from wav_io import load_wav_mono

SAMPLE_RATE = 44100
_CLICK_FADE_MS = 4.0
PREVIEW_LOOP_COUNT = 3


def ensure_pygame_mixer(sample_rate: int = SAMPLE_RATE, buffer: int = 2048) -> None:
    if not pygame.mixer.get_init():
        pygame.mixer.pre_init(frequency=sample_rate, size=-16, channels=2, buffer=buffer)
        pygame.mixer.init()


def declick(audio: np.ndarray, sample_rate: int) -> np.ndarray:
    """Remove DC offset and apply short fades to prevent pops on every hit."""
    if len(audio) == 0:
        return audio
    out = audio.astype(np.float32, copy=True)
    window = min(len(out), max(64, sample_rate // 100))
    out -= float(np.mean(out[:window]))

    fade_in = min(len(out), int(sample_rate * (_CLICK_FADE_MS / 1000.0)))
    if fade_in > 1:
        out[:fade_in] *= np.linspace(0.0, 1.0, fade_in, dtype=np.float32)

    fade_out = min(len(out), int(sample_rate * 0.003))
    if fade_out > 1:
        out[-fade_out:] *= np.linspace(1.0, 0.0, fade_out, dtype=np.float32)
    return out


def resample(audio: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if src_rate == dst_rate or len(audio) < 2:
        return audio.astype(np.float32, copy=False)
    n = int(len(audio) * dst_rate / src_rate)
    if n < 1:
        return audio.astype(np.float32, copy=False)
    x_old = np.linspace(0.0, 1.0, len(audio), dtype=np.float32)
    x_new = np.linspace(0.0, 1.0, n, dtype=np.float32)
    return np.interp(x_new, x_old, audio).astype(np.float32)


def load_sample_mono(path: Path, target_rate: int = SAMPLE_RATE) -> np.ndarray:
    audio, sr = load_wav_mono(path)
    audio = declick(audio, sr)
    return resample(audio, sr, target_rate)


def soft_limit(mix: np.ndarray, peak: float = 0.92) -> np.ndarray:
    """Normalize with headroom; tanh soft-knee above threshold reduces harsh clipping."""
    if len(mix) == 0:
        return mix
    max_val = float(np.max(np.abs(mix)))
    if max_val <= 1e-9:
        return mix
    out = mix * (peak / max_val)
    knee = 0.85
    hot = np.abs(out) > knee
    if np.any(hot):
        out = out.copy()
        out[hot] = np.sign(out[hot]) * (knee + (1.0 - knee) * np.tanh((np.abs(out[hot]) - knee) / (1.0 - knee)))
    return out.astype(np.float32)


def mono_to_pygame_sound(mono: np.ndarray, sample_rate: int = SAMPLE_RATE) -> pygame.mixer.Sound:
    ensure_pygame_mixer(sample_rate)
    clipped = np.clip(mono, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    stereo = np.column_stack([pcm, pcm])
    return pygame.sndarray.make_sound(stereo)


def wav_to_pygame_sound(path: Path) -> pygame.mixer.Sound:
    return mono_to_pygame_sound(load_sample_mono(path))
