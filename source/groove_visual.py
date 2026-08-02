"""Map MIDI groove hits to kit image regions for play-along visuals."""

from __future__ import annotations

from pathlib import Path

import mido

from kit_ui import PAD_TO_PIECE
from library_parser import DrumKit
from mido_compat import MIDI_READ_ERRORS
from midi_drum_map import resolve_pad_name

PIECE_ALIASES: dict[str, str] = {
    "Crash": "Ride",
    "Snare2": "Tom",
}


def _pad_to_piece(pad: str | None) -> str | None:
    if not pad:
        return None
    piece = PAD_TO_PIECE.get(pad)
    if piece:
        return PIECE_ALIASES.get(piece, piece)
    return None


def extract_groove_visual_hits(path: Path, kit: DrumKit) -> tuple[list[tuple[float, str]], float]:
    """Return (time_sec, kit_piece) hits and total groove length in seconds."""
    try:
        midi = mido.MidiFile(str(path))
    except MIDI_READ_ERRORS:
        return [], 0.0

    tempo = 500000
    hits: list[tuple[float, str]] = []
    end_sec = 0.0

    for track in midi.tracks:
        tick = 0
        track_tempo = tempo
        for msg in track:
            tick += msg.time
            if msg.type == "set_tempo":
                track_tempo = msg.tempo
            sec = mido.tick2second(tick, midi.ticks_per_beat, track_tempo)
            end_sec = max(end_sec, sec)
            if msg.type != "note_on" or msg.velocity <= 0:
                continue
            pad = resolve_pad_name(kit, msg.note, groove_playback=True)
            piece = _pad_to_piece(pad)
            if piece:
                hits.append((sec, piece))

    hits.sort(key=lambda item: item[0])
    if end_sec <= 0 and hits:
        end_sec = hits[-1][0] + 0.25
    return _dedupe_hits(hits), end_sec


def _dedupe_hits(hits: list[tuple[float, str]], min_gap: float = 0.035) -> list[tuple[float, str]]:
    """Drop duplicate flashes on the same drum within a few ms."""
    out: list[tuple[float, str]] = []
    last: dict[str, float] = {}
    for t_sec, piece in hits:
        prev = last.get(piece, -1.0)
        if t_sec - prev < min_gap:
            continue
        out.append((t_sec, piece))
        last[piece] = t_sec
    return out
