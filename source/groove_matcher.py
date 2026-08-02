"""Match guitar audio to grooves — BPM, rhythm feel, key, and deep features."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from audio_analyze import AudioAnalysis, _mfcc_profile
from audio_loops import AudioLoopInfo
from groove_bpm_cache import groove_bpm_label
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


def _is_partial_stem(name: str) -> bool:
    stem = name.lower()
    if "fill" in stem and "groove" not in stem:
        return True
    if "_hats_" in stem or stem.startswith("hats_"):
        if not any(x in stem for x in ("kick", "snare", "groove", "beat", "full")):
            return True
    if "_ride_" in stem and "groove" not in stem:
        return True
    return False


def _combined_score(
    bpm_delta: float,
    bpm_conf: float,
    rhythm: float,
    key: float,
    feel: float,
    energy: float,
    name: str,
    *,
    partial: bool = False,
) -> float:
    bpm_score = max(0.0, 100.0 - bpm_delta * 3.0) * (0.55 + 0.45 * bpm_conf)
    rhythm_pct = rhythm * 100.0
    key_pct = key * 100.0
    feel_pct = feel * 100.0
    energy_pct = energy * 100.0

    total = (
        bpm_score * 0.38
        + rhythm_pct * 0.42
        + key_pct * 0.08
        + feel_pct * 0.07
        + energy_pct * 0.05
    )
    if partial:
        total *= 0.72
    elif "groove" in name.lower() and "fill" not in name.lower():
        total += 2.0
    return min(100.0, total)


def find_matches(
    analysis: AudioAnalysis,
    midi_grooves: list[GrooveInfo],
    audio_loops: list[AudioLoopInfo],
    limit: int = 60,
    bpm_prefilter: int = 900,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[GrooveMatch]:
    detected = analysis.bpm
    conf = analysis.bpm_confidence
    guitar_sig = analysis.rhythm_signature
    candidates: list[GrooveMatch] = []

    prelim: list[tuple[str, Path, str, str, str, float, bool]] = []
    for g in midi_grooves:
        bpm_label = groove_bpm_label(g.path, g.bpm)
        d = _best_bpm_delta(detected, bpm_label)
        partial = _is_partial_stem(g.name)
        prelim.append(("mid", g.path, g.name, g.genre or g.pack, bpm_label, d, partial))
    for loop in audio_loops:
        bpm_label = loop.bpm or groove_bpm_label(loop.path)
        d = _best_bpm_delta(detected, bpm_label)
        prelim.append(("wav", loop.path, loop.name, loop.genre, bpm_label, d, False))

    prelim.sort(key=lambda x: x[5])
    prefilter = prelim[: min(bpm_prefilter, len(prelim))]

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

    def _add(
        kind: str,
        path: Path,
        name: str,
        genre: str,
        bpm_label: str,
        *,
        partial: bool = False,
    ) -> None:
        delta = _best_bpm_delta(detected, bpm_label)
        bpm_use = _best_bpm_for_label(detected, bpm_label)
        fp = np.array(fingerprint_file(str(path.resolve()), kind, bpm_use), dtype=np.float32)
        rhythm = rhythm_similarity(guitar_sig, fp)
        if rhythm < 0.08 and delta > 8:
            return
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
        score = _combined_score(delta, conf, rhythm, key, feel, energy, name, partial=partial)
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

    total_prefilter = len(prefilter)
    for idx, (kind, path, name, genre, bpm_label, _, partial) in enumerate(prefilter, start=1):
        if on_progress and (idx == 1 or idx % 25 == 0 or idx == total_prefilter):
            on_progress(idx, total_prefilter)
        _add(kind, path, name, genre, bpm_label, partial=partial)

    candidates.sort(key=lambda m: (-m.score, m.bpm_delta, m.name.lower()))
    best: dict[tuple[str, Path], GrooveMatch] = {}
    for m in candidates:
        key = (m.kind, m.path.resolve())
        if key not in best or m.score > best[key].score:
            best[key] = m
    unique = sorted(best.values(), key=lambda m: (-m.score, m.bpm_delta, m.name.lower()))
    return unique[:limit]
