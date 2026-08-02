"""Simple room reverb tails for mix presets (Roomy, OnlyOh)."""

from __future__ import annotations

import threading

import pygame

# Delay (ms), relative level — approximates overhead room mic bleed.
_ROOM_TAPS: tuple[tuple[int, float], ...] = (
    (32, 0.38),
    (58, 0.26),
    (92, 0.17),
    (138, 0.11),
    (195, 0.07),
)


def play_room_tail(sound: pygame.mixer.Sound, dry_gain: float, room_send: float) -> None:
    """Layer delayed copies of a hit for an audible room / overhead feel."""
    if room_send <= 0.001 or dry_gain <= 0.001:
        return
    for delay_ms, tap in _ROOM_TAPS:
        wet = dry_gain * room_send * tap
        if wet < 0.008:
            continue
        timer = threading.Timer(delay_ms / 1000.0, _play_on_channel, args=(sound, wet))
        timer.daemon = True
        timer.start()


def _play_on_channel(sound: pygame.mixer.Sound, volume: float) -> None:
    try:
        channel = sound.play()
        if channel:
            channel.set_volume(max(0.01, min(1.0, volume)))
    except pygame.error:
        pass
