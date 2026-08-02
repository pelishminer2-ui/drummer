"""Minimal WAV loading — shared by analysis, playback, and export."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

TTPW_FOURCC = b"ttpw"
WAVE_FOURCC = b"WAVE"


def wav_format_kind(path: Path) -> str:
    """Return 'wave', 'ttpw' (Toontrack proprietary), or 'unknown'."""
    try:
        header = path.read_bytes()[:12]
    except OSError:
        return "unknown"
    if len(header) < 12 or header[:4] != b"RIFF":
        return "unknown"
    form = header[8:12]
    if form == WAVE_FOURCC:
        return "wave"
    if form == TTPW_FOURCC:
        return "ttpw"
    return "unknown"


def is_playable_wav(path: Path) -> bool:
    if wav_format_kind(path) != "wave":
        return False
    try:
        with wave.open(str(path), "rb") as wf:
            wf.getnframes()
        return True
    except (wave.Error, OSError):
        return False


def count_playable_wavs(root: Path) -> int:
    if not root.is_dir():
        return 0
    return sum(1 for p in root.rglob("*.wav") if is_playable_wav(p))


def first_wav_format(root: Path) -> str | None:
    if not root.is_dir():
        return None
    for p in root.rglob("*.wav"):
        kind = wav_format_kind(p)
        if kind in ("wave", "ttpw"):
            return kind
    return None


def load_wav_mono(path: Path) -> tuple[np.ndarray, int]:
    kind = wav_format_kind(path)
    if kind == "ttpw":
        raise ValueError(
            f"Proprietary Toontrack sample (not standard WAV): {path.name}\n"
            "Use Pack-SFZ, Pack-Punk, or export standard WAVs from your drum plugin."
        )
    if kind != "wave":
        raise ValueError(f"Not a playable WAV file: {path.name}")

    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        rate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())

    if sample_width == 2:
        data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    elif sample_width == 3:
        raw = np.frombuffer(frames, dtype=np.uint8).reshape(-1, 3)
        ints = raw[:, 0].astype(np.int32) | (raw[:, 1].astype(np.int32) << 8) | (raw[:, 2].astype(np.int32) << 16)
        ints = np.where(ints >= 8388608, ints - 16777216, ints)
        data = ints.astype(np.float32) / 8388608.0
    elif sample_width == 4:
        data = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported sample width: {sample_width}")

    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return data, rate


def load_audio_mono(path: Path) -> tuple[np.ndarray, int]:
    """Load mono audio from WAV or compressed formats (MP3/OGG) via pygame."""
    if wav_format_kind(path) == "wave":
        return load_wav_mono(path)
    if path.suffix.lower() not in {".mp3", ".ogg", ".flac"}:
        raise ValueError(f"Unsupported audio format: {path.name}")

    import pygame

    from audio_prep import ensure_pygame_mixer

    ensure_pygame_mixer(buffer=2048)
    sound = pygame.mixer.Sound(str(path))
    arr = pygame.sndarray.array(sound)
    if arr.ndim == 2:
        mono = arr.mean(axis=1)
    else:
        mono = arr
    mono = mono.astype(np.float32)
    if mono.max() > 1.0 or mono.min() < -1.0:
        mono /= 32768.0
    sr = pygame.mixer.get_init()[0]
    return mono, sr


def write_wav_mono(path: Path, samples: np.ndarray, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
