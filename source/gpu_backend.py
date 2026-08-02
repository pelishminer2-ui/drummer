"""GPU-accelerated audio analysis — NVIDIA CUDA / DirectML with CPU fallback."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

EMBED_DIM = 128
_BATCH_CHUNK = 48


@dataclass(frozen=True)
class GpuInfo:
    available: bool
    backend: str
    device_name: str

    @property
    def label(self) -> str:
        if not self.available:
            return "CPU"
        return f"{self.backend.upper()} — {self.device_name}"


_gpu_info: GpuInfo | None = None
_device: Any = None


def _resolve_device() -> tuple[Any, GpuInfo]:
    global _device, _gpu_info
    if _gpu_info is not None:
        return _device, _gpu_info

    try:
        import torch
    except ImportError:
        _device = None
        _gpu_info = GpuInfo(False, "cpu", "CPU (install torch for GPU)")
        return _device, _gpu_info

    if torch.cuda.is_available():
        _device = torch.device("cuda")
        name = torch.cuda.get_device_name(0)
        _gpu_info = GpuInfo(True, "cuda", name)
        return _device, _gpu_info

    try:
        import torch_directml

        _device = torch_directml.device()
        _gpu_info = GpuInfo(True, "directml", "DirectML GPU")
        return _device, _gpu_info
    except ImportError:
        pass

    _device = torch.device("cpu")
    _gpu_info = GpuInfo(False, "cpu", "CPU")
    return _device, _gpu_info


def get_gpu_info() -> GpuInfo:
    _, info = _resolve_device()
    return info


def gpu_enabled() -> bool:
    return get_gpu_info().available


def _torch():
    import torch

    return torch


def _to_tensor(samples: np.ndarray, device: Any):
    torch = _torch()
    return torch.from_numpy(samples.astype(np.float32)).to(device)


def _trim(samples: np.ndarray, sr: int, max_sec: float = 45.0) -> np.ndarray:
    limit = int(sr * max_sec)
    if len(samples) > limit:
        return samples[:limit]
    return samples


def gpu_chroma(samples: np.ndarray, sr: int) -> np.ndarray | None:
    """12-bin chroma via GPU STFT. Returns None if GPU unavailable."""
    device, info = _resolve_device()
    if not info.available:
        return None

    torch = _torch()
    y = _to_tensor(_trim(samples, sr, 30.0), device)
    n_fft = 4096
    hop = n_fft // 4
    if y.numel() < n_fft:
        return None

    window = torch.hann_window(n_fft, device=device)
    spec = torch.stft(y, n_fft, hop_length=hop, window=window, return_complex=True)
    magnitude = spec.abs().T  # [frames, bins]

    freqs = torch.fft.rfftfreq(n_fft, 1.0 / sr, device=device)[1:]
    mask = (freqs >= 50) & (freqs <= 2000)
    freqs = freqs[mask]
    midi = 69.0 + 12.0 * torch.log2(freqs / 440.0)
    pc = (torch.round(midi).long() % 12).unsqueeze(0).expand(magnitude.shape[0], -1)
    mag = (magnitude[:, 1:][:, mask] ** 2).clamp(min=0)

    chroma_frames = torch.zeros(magnitude.shape[0], 12, device=device)
    chroma_frames.scatter_add_(1, pc, mag)
    chroma = chroma_frames.mean(0)
    peak = chroma.max()
    if peak > 0:
        chroma = chroma / peak
    return chroma.cpu().numpy().astype(np.float32)


def _mel_filterbank(sr: int, n_fft: int, n_mels: int, device: Any) -> Any:
    torch = _torch()
    fmax = sr / 2.0
    mel_min = 2595.0 * np.log10(1.0 + 50.0 / 700.0)
    mel_max = 2595.0 * np.log10(1.0 + fmax / 700.0)
    mels = torch.linspace(mel_min, mel_max, n_mels + 2, device=device)
    hz = 700.0 * (10.0 ** (mels / 2595.0) - 1.0)
    freqs = torch.linspace(0.0, fmax, n_fft // 2 + 1, device=device)
    fb = torch.zeros(n_mels, freqs.numel(), device=device)
    for i in range(n_mels):
        f0, f1, f2 = hz[i], hz[i + 1], hz[i + 2]
        up = (freqs - f0) / (f1 - f0 + 1e-9)
        down = (f2 - freqs) / (f2 - f1 + 1e-9)
        fb[i] = torch.clamp(torch.minimum(up, down), min=0.0)
    return fb


def _gpu_log_mel(y, sr: int, n_mels: int):
    torch = _torch()
    device = y.device
    n_fft = 2048
    hop = n_fft // 4
    window = torch.hann_window(n_fft, device=device)
    spec = torch.stft(y, n_fft, hop_length=hop, window=window, return_complex=True)
    power = spec.abs().square()
    mel_fb = _mel_filterbank(sr, n_fft, n_mels, device)
    mel = mel_fb @ power
    return torch.log1p(mel)


def gpu_mfcc(samples: np.ndarray, sr: int, n_mfcc: int = 13) -> np.ndarray | None:
    """MFCC-style timbre profile on GPU."""
    device, info = _resolve_device()
    if not info.available:
        return None

    torch = _torch()
    y = _to_tensor(_trim(samples, sr, 45.0), device)
    n_fft = 2048
    if y.numel() < n_fft:
        return None

    log_mel = _gpu_log_mel(y, sr, 40).mean(dim=1)
    n_mels = log_mel.shape[0]
    k = torch.arange(n_mfcc, device=device).unsqueeze(1)
    n = torch.arange(n_mels, device=device).unsqueeze(0)
    dct = torch.cos(torch.pi / n_mels * (n + 0.5) * k)
    dct[0] *= 1.0 / torch.sqrt(torch.tensor(n_mels, device=device, dtype=torch.float32))
    dct[1:] *= torch.sqrt(torch.tensor(2.0 / n_mels, device=device, dtype=torch.float32))
    mfcc = dct @ log_mel
    return mfcc.cpu().numpy().astype(np.float32)


def gpu_deep_embedding(samples: np.ndarray, sr: int, dim: int = EMBED_DIM) -> np.ndarray | None:
    """128-d mel embedding for AI-style groove similarity and future generation."""
    device, info = _resolve_device()
    if not info.available:
        return None

    torch = _torch()
    y = _to_tensor(_trim(samples, sr, 45.0), device)
    n_fft = 2048
    if y.numel() < n_fft:
        return None

    mel = _gpu_log_mel(y, sr, dim).mean(dim=1)
    norm = torch.linalg.norm(mel)
    if norm > 1e-9:
        mel = mel / norm
    return mel.cpu().numpy().astype(np.float32)


@lru_cache(maxsize=1)
def _fixed_projection(dim: int = EMBED_DIM) -> np.ndarray:
    rng = np.random.default_rng(42)
    return rng.standard_normal((dim, dim)).astype(np.float32) / np.sqrt(dim)


def project_embedding(raw: np.ndarray) -> np.ndarray:
    """Deterministic projection for richer AI-ready feature vectors."""
    if raw.shape[0] != EMBED_DIM:
        return raw
    proj = _fixed_projection()
    out = proj @ raw
    norm = np.linalg.norm(out)
    if norm > 1e-9:
        out /= norm
    return out.astype(np.float32)


def embedding_similarity(a: np.ndarray, b: np.ndarray) -> float:
    if a.shape != b.shape or np.linalg.norm(a) < 1e-9 or np.linalg.norm(b) < 1e-9:
        return 0.0
    return float(max(0.0, np.dot(a, b)))


def batch_gpu_embeddings(
    items: list[tuple[Path, np.ndarray, int]],
) -> dict[str, np.ndarray]:
    """Batch-compute deep embeddings for many WAV clips on GPU."""
    device, info = _resolve_device()
    out: dict[str, np.ndarray] = {}
    if not info.available or not items:
        return out

    for start in range(0, len(items), _BATCH_CHUNK):
        chunk = items[start : start + _BATCH_CHUNK]
        for path, samples, sr in chunk:
            emb = gpu_deep_embedding(samples, sr)
            if emb is not None:
                out[str(path.resolve())] = project_embedding(emb)
    return out


def batch_gpu_mfcc(
    items: list[tuple[Path, np.ndarray, int]],
) -> dict[str, np.ndarray]:
    """Batch MFCC profiles for WAV loops during groove matching."""
    out: dict[str, np.ndarray] = {}
    if not items:
        return out
    for path, samples, sr in items:
        mfcc = gpu_mfcc(samples, sr)
        if mfcc is not None:
            out[str(path.resolve())] = mfcc
    return out
