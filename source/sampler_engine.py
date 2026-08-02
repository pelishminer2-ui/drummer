"""Low-latency drum sample playback."""

from __future__ import annotations

import random
from pathlib import Path

import pygame

from audio_prep import ensure_pygame_mixer, wav_to_pygame_sound
from kit_ui import PAD_ALIASES_ENGINE, PAD_TO_PIECE
from library_parser import DrumKit, DrumPad, SampleLayer
from midi_drum_map import resolve_pad_name
from mix_fx import play_room_tail


class SamplerEngine:
    def __init__(self) -> None:
        ensure_pygame_mixer(buffer=2048)
        self._cache: dict[Path, pygame.mixer.Sound] = {}
        self._note_to_pad: dict[int, str] = {}
        self.kit: DrumKit | None = None
        self.channel_volume: dict[str, float] = {}
        self.master_volume: float = 1.0
        self.room_send: float = 0.08
        self.groove_playback: bool = False

    def set_channel_volume(self, channel: str, volume: float) -> None:
        self.channel_volume[channel] = max(0.0, min(2.0, volume))

    def set_master_volume(self, volume: float) -> None:
        self.master_volume = max(0.0, min(1.5, volume))

    def set_room_send(self, amount: float) -> None:
        self.room_send = max(0.0, min(1.0, amount))

    def set_groove_playback(self, enabled: bool) -> None:
        self.groove_playback = enabled

    def _pad_gain(self, pad_name: str, velocity: int) -> float:
        piece = PAD_TO_PIECE.get(pad_name, "Kick")
        ch_vol = self.channel_volume.get(piece, 1.0)
        vel = max(0.05, min(1.0, velocity / 127))
        return vel * ch_vol * self.master_volume

    def _velocity_gain(self, velocity: int) -> float:
        vel = max(0.05, min(1.0, velocity / 127))
        return vel * self.master_volume

    def _piece_channel_volume(self, pad_name: str) -> float:
        piece = PAD_TO_PIECE.get(pad_name, "Kick")
        return self.channel_volume.get(piece, 1.0)

    def load_kit(self, kit: DrumKit) -> None:
        self.kit = kit
        self._note_to_pad.clear()
        for pad in kit.pads.values():
            for note in pad.midi_notes:
                self._note_to_pad[note] = pad.name

        self._cache.clear()
        skipped = 0
        for pad in kit.pads.values():
            for sample in pad.samples:
                if sample.path in self._cache:
                    continue
                try:
                    self._cache[sample.path] = wav_to_pygame_sound(sample.path)
                except (pygame.error, OSError, ValueError):
                    skipped += 1
        if skipped and not self._cache:
            raise RuntimeError(
                "No playable WAV samples in this kit. "
                "Studio Core / Latin Percussion use Toontrack's proprietary format — "
                "switch to Pack SFZ or Pack Punk in the library dropdown."
            )

    def _pick_sample(self, pad: DrumPad, velocity: int) -> SampleLayer | None:
        if not pad.samples:
            return None
        hard = [s for s in pad.samples if s.articulation == "H"]
        soft = [s for s in pad.samples if s.articulation == "S"]
        pool = hard if velocity >= 70 and hard else soft or hard or pad.samples
        if len(pool) == 1:
            return pool[0]
        idx = min(len(pool) - 1, int((velocity / 127) * len(pool)))
        window = pool[max(0, idx - 1) : min(len(pool), idx + 2)]
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
                ch_vol = self._piece_channel_volume(resolved)
                vel_gain = self._velocity_gain(velocity)
                if ch_vol <= 0.001 and self.room_send > 0.2:
                    if not self.groove_playback:
                        play_room_tail(sound, vel_gain, self.room_send)
                    played = True
                else:
                    dry = max(0.01, min(1.0, gain))
                    channel = sound.play()
                    if channel:
                        channel.set_volume(dry)
                        if not self.groove_playback:
                            play_room_tail(sound, dry, self.room_send)
                        played = True
        if pad.layer_with and pad.layer_with in self.kit.pads:
            layer_pad = self.kit.pads[pad.layer_with]
            layer_sample = self._pick_sample(layer_pad, max(40, velocity - 20))
            if layer_sample:
                layer_sound = self._cache.get(layer_sample.path)
                if layer_sound:
                    layer_gain = self._pad_gain(pad.layer_with, max(40, velocity - 20)) * 0.35
                    layer_channel = layer_sound.play()
                    if layer_channel:
                        layer_channel.set_volume(max(0.01, min(1.0, layer_gain)))
                        if not self.groove_playback:
                            play_room_tail(layer_sound, layer_gain, self.room_send * 0.6)
                        played = True
        return played

    def trigger_note(self, note: int, velocity: int = 100) -> None:
        if not self.kit:
            return
        pad_name = resolve_pad_name(self.kit, note, groove_playback=self.groove_playback)
        if pad_name:
            self.trigger_pad(pad_name, velocity)

    def pad_count(self) -> int:
        return len(self.kit.pads) if self.kit else 0

    def sample_count(self) -> int:
        if not self.kit:
            return 0
        return sum(len(p.samples) for p in self.kit.pads.values())
