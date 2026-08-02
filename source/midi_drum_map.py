"""GM + Toontrack groove MIDI note mapping and noise filtering."""

from __future__ import annotations

from library_parser import DrumKit, DrumPad

# Click, vinyl scratch, loop FX — never audibly trigger.
IGNORED_NOTES: frozenset[int] = frozenset(
    {
        60,  # High Q / metronome click
        84,  # Click
        108,
        109,
        110,  # Toontrack vinyl / scratch / FX
        111,
        112,
        113,
        114,
        115,
        116,
        117,
        118,
        119,
        120,
        121,
        122,
        123,
        124,
        125,
        126,
        127,
        130,  # MT Power "Plop"
    }
)

# Side-stick clicks and cymbal chokes that sound like beeps/scratches in grooves.
GROOVE_ARTIFACT_NOTES: frozenset[int] = frozenset(
    {
        37,  # Side stick — sharp click in many EZ grooves
        58,  # Crash choke / stop
    }
)

# GM + common Toontrack EZdrummer groove articulations.
EXTENDED_GM_MAP: dict[int, str] = {
    25: "tom1R",
    29: "tom1R",
    31: "tom1L",
    33: "tom1L",
    34: "kickR",
    35: "kickR",
    36: "kickR",
    38: "snareR",
    39: "snareR",
    40: "snareR",
    41: "tom1R",
    42: "hatsCL",
    43: "tom1R",
    44: "hatsCL",  # half-open / pedal hat in EZ grooves
    45: "hatsO1",
    46: "hatsO1",
    47: "tom1L",
    48: "tom1L",
    50: "tom1R",
    49: "crash1",
    51: "ride4",
    52: "crash1",
    53: "ride4",
    55: "crash1",
    57: "crash1",
    61: "hatsCL",
    62: "hatsCL",  # closed hat tip (very common in Toontrack MIDI)
    63: "hatsO1",  # open / half-open hat tip
    65: "hatsCL",  # hat pedal
    66: "tom1L",
    67: "tom1L",
    68: "tom1L",
    69: "tom1L",
    70: "tom1R",
    71: "tom1R",
    72: "tom1R",
    73: "tom1R",
    74: "tom1L",
    75: "tom1R",
    76: "tom1R",
    77: "tom1R",
    78: "tom1R",
    79: "crash1",
    80: "ride4",
    81: "ride4",
    82: "hatsCL",
}


def should_ignore_note(note: int, *, groove_playback: bool = False) -> bool:
    if note in IGNORED_NOTES:
        return True
    if groove_playback and note in GROOVE_ARTIFACT_NOTES:
        return True
    return False


def resolve_pad_name(kit: DrumKit, note: int, *, groove_playback: bool = False) -> str | None:
    if should_ignore_note(note, groove_playback=groove_playback):
        return None
    for pad in kit.pads.values():
        if note in pad.midi_notes:
            return pad.name
    pad_name = EXTENDED_GM_MAP.get(note)
    if pad_name and pad_name in kit.pads:
        return pad_name
    return None


def resolve_pad(kit: DrumKit, note: int, *, groove_playback: bool = False) -> DrumPad | None:
    pad_name = resolve_pad_name(kit, note, groove_playback=groove_playback)
    if pad_name:
        return kit.pads[pad_name]
    return None
