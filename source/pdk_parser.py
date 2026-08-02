"""Parse MT Power Drum Kit .pdk libraries and extract playable WAV samples."""

from __future__ import annotations

import re
import struct
import wave
from dataclasses import dataclass
from pathlib import Path

from library_parser import DrumKit, DrumPad, SampleLayer

PDK_FILE = "MT-PowerDrumKit-Content.pdk"
GROUP_VELOCITY = {1: 42, 2: 58, 3: 74, 4: 90, 5: 106, 6: 118}

# Engine pad names used by kit_ui / sampler_engine
PAD_BY_INSTRUMENT = {
    "Kick": "kickR",
    "Snare1": "snareR",
    "Side-Stick": "hsnareR",
    "HiHatClosed": "hatsCL",
    "HiHatHalfOpen": "hatsCL",
    "HiHatOpen": "hatsO1",
    "HiHatPedal": "hatsCL",
    "TomHi": "tom1L",
    "TomMid": "tom1R",
    "TomLow": "tom1R",
    "Ride": "ride4",
    "Bell": "ride4",
    "CrashL": "crash1",
    "CrashR": "crash1",
    "CrashRStop": "crash1",
    "Snare2": "hsnareR",
    "SnareRim": "snareR",
    "FloorTom": "tom1R",
    "Splash": "crash1",
    "China": "crash1",
    "Tambourine": "hatsCL",
}


@dataclass
class PdkSound:
    group: int
    rate: int
    bps: int
    nsmp: int
    offset: int
    offset1: int


@dataclass
class PdkInstrument:
    name: str
    midi: int
    sounds: list[PdkSound]


def _find_pdk(root: Path, filename: str | None = None) -> Path:
    name = filename or PDK_FILE
    direct = root / name
    if direct.is_file():
        return direct
    for candidate in root.rglob("*.pdk"):
        return candidate
    raise FileNotFoundError(f"No .pdk content file in {root}")


def _parse_instruments(xml: str) -> list[PdkInstrument]:
    instruments: list[PdkInstrument] = []
    sound_pat = re.compile(
        r'<Sound Group="(?P<group>\d+)"\s+Chan="\d+"\s+BPS="(?P<bps>\d+)"\s+'
        r'Rate="(?P<rate>\d+)"\s+nSmp="(?P<nsmp>\d+)"\s+Offset="(?P<off>\d+)"\s+'
        r'Offset1="(?P<off1>\d+)"'
    )
    for block in re.finditer(r'<Instrument\b[^>]*>.*?</Instrument>', xml, re.S):
        chunk = block.group(0)
        name_m = re.search(r'Name="([^"]+)"', chunk)
        midi_m = re.search(r'Midi="(\d+)"', chunk)
        if not name_m or not midi_m:
            continue
        sounds = [
            PdkSound(
                group=int(m.group("group")),
                rate=int(m.group("rate")),
                bps=int(m.group("bps")),
                nsmp=int(m.group("nsmp")),
                offset=int(m.group("off")),
                offset1=int(m.group("off1")),
            )
            for m in sound_pat.finditer(chunk)
        ]
        instruments.append(PdkInstrument(name=name_m.group(1), midi=int(midi_m.group(1)), sounds=sounds))
    return instruments


def _mono_pcm(data: bytes, sound: PdkSound) -> bytes:
    if sound.bps != 16:
        raise ValueError(f"Unsupported BPS: {sound.bps}")
    nbytes = sound.nsmp * 2
    left = data[sound.offset : sound.offset + nbytes]
    right = data[sound.offset1 : sound.offset1 + nbytes]
    if len(left) != nbytes:
        raise ValueError(f"Truncated sample at offset {sound.offset}")
    if len(right) != nbytes:
        right = left
    out = bytearray(nbytes)
    for i in range(0, nbytes, 2):
        lv = struct.unpack_from("<h", left, i)[0]
        rv = struct.unpack_from("<h", right, i)[0]
        mixed = max(-32768, min(32767, (lv + rv) // 2))
        struct.pack_into("<h", out, i, mixed)
    return bytes(out)


def _write_wav(path: Path, pcm: bytes, rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm)


def extract_pdk_samples(pdk_path: Path, sounds_dir: Path, *, force: bool = False) -> int:
    """Extract .pdk PCM into standard WAV files under Sounds/. Returns wav count."""
    marker = sounds_dir / ".pdk-extracted"
    if marker.exists() and not force and any(sounds_dir.rglob("*.wav")):
        return sum(1 for _ in sounds_dir.rglob("*.wav"))

    data = pdk_path.read_bytes()
    xml_end = data.rfind(b"</InstDef>")
    if xml_end < 0:
        raise ValueError(f"Invalid PDK (missing InstDef): {pdk_path.name}")
    xml = data[: xml_end + len(b"</InstDef>")].decode("utf-8", errors="replace")
    instruments = _parse_instruments(xml)
    if not instruments:
        raise ValueError(f"No instruments found in {pdk_path.name}")

    if sounds_dir.exists() and force:
        for wav in sounds_dir.rglob("*.wav"):
            wav.unlink()

    written = 0
    for inst in instruments:
        safe = re.sub(r"[^\w\-]+", "_", inst.name).strip("_")
        for idx, sound in enumerate(inst.sounds):
            out = sounds_dir / safe / f"{safe}_g{sound.group}_{idx:02d}.wav"
            if out.exists() and out.stat().st_size > 500 and not force:
                written += 1
                continue
            pcm = _mono_pcm(data, sound)
            _write_wav(out, pcm, sound.rate)
            written += 1

    sounds_dir.mkdir(parents=True, exist_ok=True)
    marker.write_text(pdk_path.name, encoding="utf-8")
    return written


def ensure_pdk_extracted(library_root: Path, pdk_filename: str | None = None) -> Path:
    pdk_path = _find_pdk(library_root, pdk_filename)
    sounds_dir = library_root / "Sounds"
    extract_pdk_samples(pdk_path, sounds_dir)
    return sounds_dir


def list_pdk_kits(library_root: Path) -> list[str]:
    if _find_pdk(library_root):
        return ["MT Power Drum Kit"]
    return []


def load_pdk_kit(library_root: Path, kit_name: str = "MT Power Drum Kit", pdk_filename: str | None = None) -> DrumKit:
    ensure_pdk_extracted(library_root, pdk_filename)
    pdk_path = _find_pdk(library_root, pdk_filename)
    data = pdk_path.read_bytes()
    xml_end = data.rfind(b"</InstDef>")
    xml = data[: xml_end + len(b"</InstDef>")].decode("utf-8", errors="replace")
    instruments = _parse_instruments(xml)
    sounds_dir = library_root / "Sounds"

    pads: dict[str, DrumPad] = {}
    for inst in instruments:
        pad_name = PAD_BY_INSTRUMENT.get(inst.name)
        if not pad_name:
            continue
        safe = re.sub(r"[^\w\-]+", "_", inst.name).strip("_")
        layers: list[SampleLayer] = []
        for idx, sound in enumerate(inst.sounds):
            wav = sounds_dir / safe / f"{safe}_g{sound.group}_{idx:02d}.wav"
            if not wav.exists():
                continue
            velocity = GROUP_VELOCITY.get(sound.group, 60 + sound.group * 8)
            layers.append(SampleLayer(path=wav, velocity=velocity, articulation="H"))
        if not layers:
            continue
        label = inst.name.replace("-", " ")
        if pad_name in pads:
            pads[pad_name].samples.extend(layers)
            pads[pad_name].samples.sort(key=lambda s: s.velocity)
            if inst.midi not in pads[pad_name].midi_notes:
                pads[pad_name].midi_notes.append(inst.midi)
        else:
            pads[pad_name] = DrumPad(
                name=pad_name,
                midi_notes=[inst.midi],
                samples=layers,
                label=label,
            )

    return DrumKit(name=kit_name, root=library_root, pads=pads, sample_rate=44100)


if __name__ == "__main__":
    import sys

    root = Path(__file__).resolve().parent.parent / "Libraries" / "MT-Wild-Drums"
    if len(sys.argv) > 1:
        root = Path(sys.argv[1])
    pdk = _find_pdk(root)
    sounds = root / "Sounds"
    count = extract_pdk_samples(pdk, sounds, force="--force" in sys.argv)
    kit = load_pdk_kit(root)
    print(f"Extracted {count} WAV files, {len(kit.pads)} pads, {sum(len(p.samples) for p in kit.pads.values())} layers")
