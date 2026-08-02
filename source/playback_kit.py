"""Load a playable kit for MIDI groove playback."""

from __future__ import annotations

from pathlib import Path

from folder_kit_parser import list_folder_kits, load_folder_kit
from library_parser import DrumKit, load_kit, resolve_kit_name
from library_scanner import DetectedLibrary, detect_all, load_manifest
from sfz_parser import list_sfz_kits, load_sfz_kit


def best_playback_library(libraries: list[DetectedLibrary] | None = None) -> DetectedLibrary | None:
    """Pick a library with kick, snare, hats, and cymbals for MIDI + kit clicks."""
    libs = libraries if libraries is not None else detect_all()
    # Folder (Pack Punk) and PDK (MT Wild Drums) include hats/ride; SFZ packs often do not.
    for lib in libs:
        if lib.playable_wav_count > 0 and lib.library_type in ("folder", "pdk"):
            return lib
    for lib in libs:
        if lib.playable_wav_count > 0:
            return lib
    return None


def best_groove_playback_library(libraries: list[DetectedLibrary] | None = None) -> DetectedLibrary | None:
    """Prefer folder kits for Toontrack MIDI — fewer harsh FX samples than MT Wild."""
    libs = libraries if libraries is not None else detect_all()
    for lib in libs:
        if lib.playable_wav_count > 0 and lib.library_type == "folder":
            return lib
    for lib in libs:
        if lib.playable_wav_count > 0 and lib.library_type == "pdk":
            return lib
    for lib in libs:
        if lib.playable_wav_count > 0:
            return lib
    return None


def _load_kit_from_library(lib: DetectedLibrary) -> tuple[DrumKit, str]:
    if lib.library_type == "pdk":
        from pdk_parser import list_pdk_kits, load_pdk_kit

        manifest_entry = next(
            (e for e in load_manifest().get("libraries", []) if e.get("id") == lib.library_id),
            {},
        )
        kit_name = list_pdk_kits(lib.path)[0]
        kit = load_pdk_kit(lib.path, kit_name, manifest_entry.get("pdk_file"))
    elif lib.library_type == "sfz":
        kits = list_sfz_kits(lib.path, lib.sfz_kits)
        kit_name = kits[0] if kits else "Funk Tight"
        kit = load_sfz_kit(lib.path, kit_name, lib.sfz_kits)
    elif lib.library_type == "folder":
        kits = list_folder_kits(lib.path)
        kit_name = kits[0] if kits else "Punk Kit"
        kit = load_folder_kit(lib.path, kit_name)
    else:
        kits = list(lib.kit_labels.values()) if lib.kit_labels else ["Standard Kit"]
        kit_name = kits[0]
        internal = resolve_kit_name(kit_name, lib.kit_labels)
        kit = load_kit(lib.path, internal)

    kit_label = kit.name if hasattr(kit, "name") else kit_name
    return kit, kit_label


def load_playback_kit(libraries: list[DetectedLibrary] | None = None) -> tuple[DrumKit, str, str]:
    """Return (kit, library_label, kit_label). Raises if no playable library exists."""
    lib = best_playback_library(libraries)
    if not lib:
        raise RuntimeError("No playable WAV library found. Import Pack SFZ or Pack Punk.")
    kit, kit_label = _load_kit_from_library(lib)
    return kit, lib.name, kit_label


def load_groove_playback_kit(libraries: list[DetectedLibrary] | None = None) -> tuple[DrumKit, str, str]:
    """Clean kit for MIDI groove preview (Pack Punk preferred over MT Wild FX samples)."""
    lib = best_groove_playback_library(libraries)
    if not lib:
        raise RuntimeError("No playable WAV library found. Import Pack SFZ or Pack Punk.")
    kit, kit_label = _load_kit_from_library(lib)
    return kit, lib.name, kit_label


def needs_playback_fallback(detected: DetectedLibrary | None) -> bool:
    if not detected:
        return True
    return detected.playable_wav_count == 0 or detected.sample_format == "ttpw"
