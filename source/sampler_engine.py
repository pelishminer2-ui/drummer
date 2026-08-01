"""Low-latency drum sample playback."""

from __future__ import annotations

import random
from pathlib import Path

import pygame

from library_parser import DrumKit, DrumPad, SampleLayer
from kit_ui import PAD_ALIASES_ENGINE, PAD_TO_PIECE


class SamplerEngine:
    def __init__(self) -> None:
        pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=256)
        pygame.mixer.init()
        self._cache: dict[Path, pygame.mixer.Sound] = {}
        self._note_to_pad: dict[int, str] = {}
        self.kit: DrumKit | None = None
        self.channel_volume: dict[str, float] = {}
        self.master_volume: float = 1.0

    def set_channel_volume(self, channel: str, volume: float) -> None:
        self.channel_volume[channel] = max(0.0, min(2.0, volume))

    def set_master_volume(self, volume: float) -> None:
        self.master_volume = max(0.0, min(1.5, volume))

    def _pad_gain(self, pad_name: str, velocity: int) -> float:
        piece = PAD_TO_PIECE.get(pad_name, "Kick")
        ch_vol = self.channel_volume.get(piece, 1.0)
        vel = max(0.05, min(1.0, velocity / 127))
        return vel * ch_vol * self.master_volume

    def load_kit(self, kit: DrumKit) -> None:
        self.kit = kit
        self._note_to_pad.clear()
        for pad in kit.pads.values():
            for note in pad.midi_notes:
                self._note_to_pad[note] = pad.name

        self._cache.clear()
        for pad in kit.pads.values():
            for sample in pad.samples:
                if sample.path not in self._cache:
                    self._cache[sample.path] = pygame.mixer.Sound(str(sample.path))

    def _pick_sample(self, pad: DrumPad, velocity: int) -> SampleLayer | None:
        if not pad.samples:
            return None
        hard = [s for s in pad.samples if s.articulation == "H"]
        soft = [s for s in pad.samples if s.articulation == "S"]
        pool = hard if velocity >= 70 and hard else soft or hard or pad.samples
        if len(pool) == 1:
            return pool[0]
        idx = min(len(pool) - 1, int((velocity / 127) * len(pool)))
        window = pool[max(0, idx - 1): min(len(pool), idx + 2)]
        return random.choice(window)

    def trigger_pad(self, pad_name: str, velocity: int = 100) -> bool:
        if not self.kit:
            return False
        resolved = pad_name
        if pad_name not in self.kit.pads:
            for alias in PAD_ALIASES_ENGINE.get(pad_name, []):
                if alias in self.kit.pads:
                    resolved = alias
                    break
            else:
                return False
        pad = self.kit.pads[resolved]
        gain = self._pad_gain(resolved, velocity)
        sample = self._pick_sample(pad, velocity)
        played = False
        if sample:
            sound = self._cache.get(sample.path)
            if sound:
                sound.set_volume(max(0.01, min(1.0, gain)))
                sound.play()
                played = True
        if pad.layer_with and pad.layer_with in self.kit.pads:
            layer_pad = self.kit.pads[pad.layer_with]
            layer_sample = self._pick_sample(layer_pad, max(40, velocity - 20))
            if layer_sample:
                layer_sound = self._cache.get(layer_sample.path)
                if layer_sound:
                    layer_gain = self._pad_gain(pad.layer_with, max(40, velocity - 20)) * 0.35
                    layer_sound.set_volume(max(0.01, min(1.0, layer_gain)))
                    layer_sound.play()
                    played = True
        return played

    def trigger_note(self, note: int, velocity: int = 100) -> None:
        pad_name = self._note_to_pad.get(note)
        if pad_name:
            self.trigger_pad(pad_name, velocity)
        else:
            self._trigger_gm_fallback(note, velocity)

    def _trigger_gm_fallback(self, note: int, velocity: int) -> None:
        gm_map = {
            36: "kickR", 35: "kickR", 34: "kickR",
            38: "snareR", 39: "snareR", 37: "snareR", 40: "snareR",
            42: "hatsCL", 44: "hatsCL", 46: "hatsO1",
            49: "ride4", 51: "ride4", 57: "ride4",
            41: "tom1R", 43: "tom1R", 45: "tom1L", 47: "tom1L",
            48: "tom1L", 50: "tom1R",
        }
        pad_name = gm_map.get(note)
        if pad_name:
            self.trigger_pad(pad_name, velocity)

    def pad_count(self) -> int:
        return len(self.kit.pads) if self.kit else 0

    def sample_count(self) -> int:
        if not self.kit:
            return 0
        return sum(len(p.samples) for p in self.kit.pads.values())
