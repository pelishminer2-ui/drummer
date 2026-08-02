"""Render MIDI grooves to standard WAV for export and drag-out."""

from __future__ import annotations

from pathlib import Path

from groove_render import render_midi_to_wav as _render_midi_to_wav
from library_parser import DrumKit


def render_midi_to_wav(midi_path: Path, kit: DrumKit, output_path: Path, sample_rate: int = 44100) -> Path:
    """Offline render a MIDI groove through the loaded kit to a standard WAV file."""
    return _render_midi_to_wav(midi_path, kit, output_path, sample_rate=sample_rate)
