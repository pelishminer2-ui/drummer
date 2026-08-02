"""Format file paths for native drag-and-drop (Windows/macOS/Linux via tkdnd)."""

from __future__ import annotations

from pathlib import Path


def format_dnd_files(paths: list[Path]) -> str:
    """Return a tkdnd DND_FILES payload for one or more absolute paths."""
    parts: list[str] = []
    for raw in paths:
        text = str(raw.resolve()).replace("\\", "/")
        if " " in text or "{" in text or "}" in text:
            parts.append(f"{{{text}}}")
        else:
            parts.append(text)
    return " ".join(parts)
