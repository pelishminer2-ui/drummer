"""Match guitar audio to grooves — BPM, rhythm feel, key, and deep features."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from audio_analyze import AudioAnalysis, _mfcc_profile
from audio_loops import AudioLoopInfo
from gpu_backend import batch_gpu_embeddings, batch_gpu_mfcc, embedding_similarity
from midi_grooves import GrooveInfo
from rhythm_fingerprint import fingerprint_file, rhythm_similarity


@dataclass
class GrooveMatch:
    kind: str
    path: Path
    name: str
    genre: str
    bpm_label: str
    score: float
    bpm_delta: float
    rhythm_score: float = 0.0
    key_score: float = 0.0
    feel_score: float = 0.0


def _parse_bpm_range(label: str) -> tuple[float, float] | None:
    if not label:
        return None
    label = label.strip()
    range_match = re.match(r"(\d+)\s*-\s*(\d+)", label)
    if range_match:
        lo, hi = int(range_match.group(1)), int(range_match.group(2))
        return float(lo), float(hi)
    single = re.search(r"(\d{2,3})", label)
    if single:
        v = float(single.group(1))
        return v, v
    return None


def bpm_candidates(detected: float) -> list[float]:
    cands: set[float] = set()
    for mult in (0.25, 0.5, 1.0, 2.0, 4.0):
        v = detected * mult
        if 60 <= v <= 300:
            cands.add(round(v, 1))
    return sorted(cands) or [detected]


def _bpm_distance(detected: float, label: str) -> float:
    parsed = _parse_bpm_range(label)
    if not parsed:
        return 50.0
    lo, hi = parsed
    if lo <= detected <= hi:
        return 0.0
    if detected < lo:
        return lo - detected
    return detected - hi


def _best_bpm_delta(detected: float, label: str) -> float:
    return min(_bpm_distance(c, label) for c in bpm_candidates(detected))


def _best_bpm_for_label(detected: float, label: str) -> float:
    return min(bpm_candidates(detected), key=lambda c: _bpm_distance(c, label))


# Genre / name hints for key-mode compatibility
_MINOR_GENRES = ("ballad", "blues", "minor", "sad", "dark", "metal")
_MAJOR_GENRES = ("pop", "rock", "funk", "motown", "happy", "country", "punk")
_HIGH_ENERGY = ("punk", "metal", "rock", "funk", "upbeat", "fast")


def _key_compatibility(analysis: AudioAnalysis, genre: str, name: str) -> float:
    if analysis.key_root == "?":
        return 0.5
    text = f"{genre} {name}".lower()
    score = 0.5
    if analysis.key_mode == "minor":
        if any(g in text for g in _MINOR_GENRES):
            score += 0.35
        if any(g in text for g in _MAJOR_GENRES) and "ballad" not in text:
            score -= 0.1
    else:
        if any(g in text for g in _MAJOR_GENRES):
            score += 0.35
        if any(g in text for g in _MINOR_GENRES) and "ballad" in text:
            score += 0.15
    # Power-chord keys (E, A, G) suit rock/punk
    if analysis.key_root in ("E", "A", "G", "D") and ("punk" in text or "rock" in text):
        score += 0.15
    return max(0.0, min(1.0, score))


def _feel_similarity(analysis: AudioAnalysis, groove_mfcc: np.ndarray, groove_emb: np.ndarray | None = None) -> float:
    scores: list[float] = []
    a = analysis.mfcc_profile
    b = groove_mfcc
    if np.linalg.norm(a) >= 1e-9 and np.linalg.norm(b) >= 1e-9:
        scores.append(float(max(0.0, np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))))
    if groove_emb is not None and np.linalg.norm(analysis.deep_embedding) >= 1e-9:
        scores.append(embedding_similarity(analysis.deep_embedding, groove_emb))
    return max(scores) if scores else 0.0


def _energy_match(analysis: AudioAnalysis, genre: str, name: str) -> float:
    text = f"{genre} {name}".lower()
    high = any(g in text for g in _HIGH_ENERGY)
    if analysis.energy > 0.08 and high:
        return 0.9
    if analysis.energy <= 0.08 and not high:
        return 0.8
    if analysis.brightness > 0.25 and high:
        return 0.75
    return 0.5


def _combined_score(
    bpm_delta: float,
    bpm_conf: float,
    rhythm: float,
    key: float,
    feel: float,
    energy: float,
    name: str,
) -> float:
    bpm_score = max(0.0, 100.0 - bpm_delta * 2.5) * (0.5 + 0.5 * bpm_conf)
    rhythm_pct = rhythm * 100.0
    key_pct = key * 100.0
    feel_pct = feel * 100.0
    energy_pct = energy * 100.0

    total = (
        bpm_score * 0.30
        + rhythm_pct * 0.35
        + key_pct * 0.15
        + feel_pct * 0.10
        + energy_pct * 0.10
    )
    if "groove" in name.lower() and "fill" not in name.lower():
        total += 3.0
    return min(100.0, total)


def find_matches(
    analysis: AudioAnalysis,
    midi_grooves: list[GrooveInfo],
    audio_loops: list[AudioLoopInfo],
    limit: int = 60,
    bpm_prefilter: int = 400,
) -> list[GrooveMatch]:
    detected = analysis.bpm
    conf = analysis.bpm_confidence
    guitar_sig = analysis.rhythm_signature
    candidates: list[GrooveMatch] = []

    prelim: list[tuple[str, Path, str, str, str, float]] = []
    for g in midi_grooves:
        d = _best_bpm_delta(detected, g.bpm)
        prelim.append(("mid", g.path, g.name, g.genre or g.pack, g.bpm or "?", d))
    for loop in audio_loops:
        d = _best_bpm_delta(detected, loop.bpm)
        prelim.append(("wav", loop.path, loop.name, loop.genre, loop.bpm or "?", d))

    prelim.sort(key=lambda x: x[5])
    prefilter = prelim[:bpm_prefilter]

    wav_items: list[tuple[Path, np.ndarray, int]] = []
    if any(k == "wav" for k, *_ in prefilter):
        from wav_io import load_audio_mono

        for kind, path, name, genre, bpm_label, _ in prefilter:
            if kind != "wav":
                continue
            try:
                samples, sr = load_audio_mono(path)
                wav_items.append((path, samples, sr))
            except (OSError, ValueError):
                pass

    gpu_mfcc_map = batch_gpu_mfcc(wav_items)
    gpu_emb_map = batch_gpu_embeddings(wav_items)

    def _add(kind: str, path: Path, name: str, genre: str, bpm_label: str) -> None:
        delta = _best_bpm_delta(detected, bpm_label)
        bpm_use = _best_bpm_for_label(detected, bpm_label)
        fp = np.array(fingerprint_file(str(path.resolve()), kind, bpm_use), dtype=np.float32)
        rhythm = rhythm_similarity(guitar_sig, fp)
        key = _key_compatibility(analysis, genre, name)
        feel = rhythm * 0.5 + _energy_match(analysis, genre, name) * 0.5
        path_key = str(path.resolve())
        if kind == "wav":
            loop_mfcc = gpu_mfcc_map.get(path_key)
            loop_emb = gpu_emb_map.get(path_key)
            if loop_mfcc is None:
                try:
                    from wav_io import load_audio_mono

                    samples, sr = load_audio_mono(path)
                    loop_mfcc = _mfcc_profile(samples, sr)
                except (OSError, ValueError):
                    loop_mfcc = None
            if loop_mfcc is not None:
                feel = max(feel, _feel_similarity(analysis, loop_mfcc, loop_emb))
            elif loop_emb is not None:
                feel = max(feel, embedding_similarity(analysis.deep_embedding, loop_emb))
        energy = _energy_match(analysis, genre, name)
        score = _combined_score(delta, conf, rhythm, key, feel, energy, name)
        candidates.append(
            GrooveMatch(
                kind=kind,
                path=path,
                name=name,
                genre=genre,
                bpm_label=bpm_label,
                score=score,
                bpm_delta=delta,
                rhythm_score=rhythm,
                key_score=key,
                feel_score=feel,
            )
        )

    for kind, path, name, genre, bpm_label, _ in prefilter:
        _add(kind, path, name, genre, bpm_label)

    candidates.sort(key=lambda m: (-m.score, m.bpm_delta))
    return candidates[:limit]
