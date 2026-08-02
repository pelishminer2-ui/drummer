"""GM + Toontrack groove MIDI note mapping and noise filtering."""

from __future__ import annotations

from pathlib import Path

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
        40,  # Rim shot
        52,  # China cymbal
        55,  # Splash
        57,  # Ride bell mapped as crash
        58,  # Crash choke / stop
        81,  # Ride bell
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
    54: "tom1L",
    55: "crash1",
    56: "tom1R",  # cowbell
    57: "crash1",
    59: "ride4",
    64: "tom1L",  # conga / percussion
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
    86: "tom1L",  # shaker / percussion in hip-hop leads (fallback tom)
    88: "tom1L",
    91: "tom1L",
    83: "tom1L",
    87: "tom1L",
    90: "ride4",
    93: "tom1R",
    95: "tom1R",
    96: "tom1L",
    98: "ride4",
    100: "crash1",
    24: "kickR",
    26: "kickR",
    28: "tom1R",
    30: "tom1L",
    32: "tom1L",
}

# When a library kit lacks a pad (e.g. Pack Punk has no open hat), use these substitutes.
PAD_FALLBACKS: dict[str, list[str]] = {
    "hatsO1": ["hatsCL"],
    "hatsPL": ["hatsCL"],
    "hsnareR": ["snareR"],
    "tom1L": ["tom1R"],
    "ride4": ["crash1"],
    "crash1": ["ride4"],
}


def _pitch_fallback_pad(kit: DrumKit, note: int) -> str | None:
    """Map unmapped melodic/bass/lead notes to the nearest drum pad for preview."""
    if note <= 35:
        candidates = ["kickR", "tom1R", "tom1L"]
    elif note <= 50:
        candidates = ["tom1R", "tom1L", "kickR", "snareR"]
    elif note <= 65:
        candidates = ["snareR", "hatsCL", "tom1L", "tom1R"]
    elif note <= 80:
        candidates = ["hatsCL", "hatsO1", "ride4", "tom1R"]
    else:
        candidates = ["ride4", "crash1", "hatsCL", "tom1L"]
    for name in candidates:
        if name in kit.pads:
            return name
        for alt in PAD_FALLBACKS.get(name, []):
            if alt in kit.pads:
                return alt
    return next(iter(kit.pads.keys()), None)


def classify_groove_midi(midi_path: Path) -> str:
    """Return drums | bass | lead | fx for user-facing messages."""
    parts = {p.lower() for p in midi_path.parts}
    stem = midi_path.stem.lower()
    if "bass-lines" in parts or stem.endswith("_bs") or "bass" in stem:
        return "bass"
    if "leads" in parts or stem.endswith("_lead") or "lead" in stem:
        return "lead"
    if stem.endswith("_fx") or "sound fx" in parts:
        return "fx"
    return "drums"


def should_ignore_note(
    note: int,
    *,
    groove_playback: bool = False,
    allow_clicks: bool = False,
) -> bool:
    if note in IGNORED_NOTES:
        if allow_clicks and note in {60, 84}:
            return False
        return True
    if groove_playback and note in GROOVE_ARTIFACT_NOTES:
        return True
    return False


def resolve_pad_name(
    kit: DrumKit,
    note: int,
    *,
    groove_playback: bool = False,
    allow_clicks: bool = False,
) -> str | None:
    if should_ignore_note(note, groove_playback=groove_playback, allow_clicks=allow_clicks):
        return None
    for pad in kit.pads.values():
        if note in pad.midi_notes:
            return pad.name
    if allow_clicks and note in {60, 84}:
        return _pitch_fallback_pad(kit, 42)
    pad_name = EXTENDED_GM_MAP.get(note)
    if pad_name:
        if pad_name in kit.pads:
            return pad_name
        for alt in PAD_FALLBACKS.get(pad_name, []):
            if alt in kit.pads:
                return alt
    if groove_playback:
        return _pitch_fallback_pad(kit, note)
    return None


def resolve_pad(
    kit: DrumKit,
    note: int,
    *,
    groove_playback: bool = False,
    allow_clicks: bool = False,
) -> DrumPad | None:
    pad_name = resolve_pad_name(
        kit, note, groove_playback=groove_playback, allow_clicks=allow_clicks
    )
    if pad_name:
        return kit.pads[pad_name]
    return None
