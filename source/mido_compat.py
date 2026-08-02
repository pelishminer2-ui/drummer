"""mido version compatibility — older wheels lack MidiFileError."""

from __future__ import annotations

import mido

try:
    MIDI_READ_ERRORS: tuple[type[BaseException], ...] = (OSError, mido.MidiFileError, ValueError)
except AttributeError:
    MIDI_READ_ERRORS = (OSError, ValueError)
