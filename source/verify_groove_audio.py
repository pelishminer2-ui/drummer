#!/usr/bin/env python3
"""Verify MIDI groove audio path — render + playback prep."""

from __future__ import annotations

import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parent
sys.path.insert(0, str(SOURCE))

from groove_render import parse_midi_events, render_midi_to_buffer
from midi_drum_map import should_ignore_note
from playback_kit import load_playback_kit


def main() -> int:
    lib_root = SOURCE.parent / "Libraries"
    midi = next(lib_root.rglob("EZ Demo*.mid"), None)
    if not midi:
        midi = next(lib_root.rglob("*.mid"), None)
    if not midi:
        print("FAIL: no .mid files under Libraries")
        return 1

    kit, lib_name, kit_name = load_playback_kit()
    events = parse_midi_events(midi)
    ignored = sum(1 for _, n, _ in events if should_ignore_note(n, groove_playback=True))
    buffer = render_midi_to_buffer(midi, kit)
    peak = float(buffer.max())

    print(f"OK kit={kit_name} ({lib_name})")
    print(f"OK midi={midi.name} events={len(events)} ignored={ignored} samples={len(buffer)} peak={peak:.3f}")
    if len(buffer) < 44100:
        print("FAIL: render too short")
        return 1
    if peak <= 0.01:
        print("FAIL: render silent")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
