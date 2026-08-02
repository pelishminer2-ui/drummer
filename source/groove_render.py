"""Render MIDI grooves to a mixed audio buffer — click-free, WAV-smooth playback."""

from __future__ import annotations

from pathlib import Path

import mido
import numpy as np

from audio_prep import SAMPLE_RATE, declick, load_sample_mono, resample, soft_limit
from kit_ui import PAD_TO_PIECE
from library_parser import DrumKit, DrumPad, SampleLayer
from midi_drum_map import resolve_pad
from wav_io import load_wav_mono, write_wav_mono

_TAIL_PAD_SEC = 1.5
_sample_cache: dict[str, np.ndarray] = {}


def parse_midi_events(midi_path: Path) -> list[tuple[float, int, int]]:
    midi = mido.MidiFile(str(midi_path))
    tempo = 500000
    events: list[tuple[float, int, int]] = []

    for track in midi.tracks:
        tick = 0
        track_tempo = tempo
        for msg in track:
            tick += msg.time
            if msg.type == "set_tempo":
                track_tempo = msg.tempo
            if msg.type == "note_on" and msg.velocity > 0:
                sec = mido.tick2second(tick, midi.ticks_per_beat, track_tempo)
                events.append((sec, msg.note, msg.velocity))

    events.sort(key=lambda item: item[0])
    return events


def _pick_sample(pad: DrumPad, velocity: int) -> SampleLayer | None:
    if not pad.samples:
        return None
    hard = [s for s in pad.samples if s.articulation == "H"]
    soft = [s for s in pad.samples if s.articulation == "S"]
    pool = hard if velocity >= 70 and hard else soft or hard or pad.samples
    idx = min(len(pool) - 1, int((velocity / 127) * len(pool)))
    return pool[idx]


def _sample_key(path: Path) -> str:
    try:
        st = path.stat()
        return f"{path.resolve()}:{st.st_mtime_ns}:{st.st_size}"
    except OSError:
        return str(path.resolve())


def _get_sample_audio(path: Path) -> np.ndarray | None:
    key = _sample_key(path)
    cached = _sample_cache.get(key)
    if cached is not None:
        return cached
    try:
        audio = load_sample_mono(path, SAMPLE_RATE)
    except (OSError, ValueError):
        return None
    if len(_sample_cache) > 512:
        _sample_cache.clear()
    _sample_cache[key] = audio
    return audio


def _load_sample_cache(kit: DrumKit) -> dict[Path, np.ndarray]:
    cache: dict[Path, np.ndarray] = {}
    for pad in kit.pads.values():
        for sample in pad.samples:
            if sample.path in cache:
                continue
            audio = _get_sample_audio(sample.path)
            if audio is not None:
                cache[sample.path] = audio
    return cache


def _hit_gain(pad_name: str, velocity: int, channel_volume: dict[str, float], master_volume: float) -> float:
    piece = PAD_TO_PIECE.get(pad_name, "Kick")
    ch_vol = channel_volume.get(piece, 1.0)
    vel = max(0.05, min(1.0, velocity / 127.0))
    return vel * ch_vol * master_volume


def render_midi_to_buffer(
    midi_path: Path,
    kit: DrumKit,
    *,
    sample_rate: int = SAMPLE_RATE,
    channel_volume: dict[str, float] | None = None,
    master_volume: float = 1.0,
) -> np.ndarray:
    """Mix a MIDI groove into one continuous mono buffer (same path as WAV export)."""
    events = parse_midi_events(midi_path)
    if not events:
        raise ValueError("MIDI file has no drum notes to render.")

    ch_vol = channel_volume or {}
    cache = _load_sample_cache(kit)
    if not cache:
        raise ValueError("No playable WAV samples in the current kit.")

    end_sec = events[-1][0] + _TAIL_PAD_SEC
    total_frames = int(end_sec * sample_rate) + sample_rate
    mix = np.zeros(total_frames, dtype=np.float32)

    for sec, note, velocity in events:
        pad = resolve_pad(kit, note, groove_playback=True)
        if not pad:
            continue
        sample = _pick_sample(pad, velocity)
        if not sample or sample.path not in cache:
            continue

        audio = cache[sample.path]
        if sample_rate != SAMPLE_RATE:
            audio = resample(audio, SAMPLE_RATE, sample_rate)
        start = int(sec * sample_rate)
        if start >= total_frames:
            continue
        length = min(len(audio), total_frames - start)
        gain = _hit_gain(pad.name, velocity, ch_vol, master_volume)
        mix[start : start + length] += audio[:length] * gain

    mix = soft_limit(mix, peak=0.92)

    tail_fade = min(len(mix), int(sample_rate * 0.02))
    if tail_fade > 1:
        mix[-tail_fade:] *= np.linspace(1.0, 0.0, tail_fade, dtype=np.float32)
    return mix


def buffer_to_pygame_sound(mono: np.ndarray, sample_rate: int = SAMPLE_RATE):
    from audio_prep import mono_to_pygame_sound

    return mono_to_pygame_sound(mono, sample_rate)


def render_midi_to_wav(
    midi_path: Path,
    kit: DrumKit,
    output_path: Path,
    sample_rate: int = SAMPLE_RATE,
) -> Path:
    mix = render_midi_to_buffer(midi_path, kit, sample_rate=sample_rate)
    write_wav_mono(output_path, mix, sample_rate)
    return output_path
