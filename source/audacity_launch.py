"""Find Audacity on Windows and open audio files in it."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

DEFAULT_PATHS = (
    Path(r"C:\Program Files\Audacity\Audacity.exe"),
    Path(r"C:\Program Files (x86)\Audacity\Audacity.exe"),
)

_cached_exe: Path | None = None


def find_audacity_exe() -> Path | None:
    """Return Audacity.exe if installed, else None."""
    global _cached_exe
    if _cached_exe and _cached_exe.is_file():
        return _cached_exe

    override = os.environ.get("AUDACITY_EXE", "").strip()
    if override:
        path = Path(override)
        if path.is_file():
            _cached_exe = path
            return path

    for path in DEFAULT_PATHS:
        if path.is_file():
            _cached_exe = path
            return path

    if sys.platform == "win32":
        try:
            import winreg

            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    with winreg.OpenKey(hive, r"Software\Microsoft\Windows\CurrentVersion\Uninstall") as root:
                        for i in range(winreg.QueryInfoKey(root)[0]):
                            try:
                                sub_name = winreg.EnumKey(root, i)
                                with winreg.OpenKey(root, sub_name) as sub:
                                    name = winreg.QueryValueEx(sub, "DisplayName")[0]
                                    if "audacity" not in str(name).lower():
                                        continue
                                    loc = winreg.QueryValueEx(sub, "InstallLocation")[0]
                                    if not loc:
                                        continue
                                    exe = Path(str(loc)) / "Audacity.exe"
                                    if exe.is_file():
                                        _cached_exe = exe
                                        return exe
                            except OSError:
                                continue
                except OSError:
                    continue
        except ImportError:
            pass

    return None


def open_in_audacity(audio_path: Path) -> Path:
    """Launch Audacity with an audio file. Returns the Audacity executable used."""
    wav = audio_path.resolve()
    if not wav.is_file():
        raise FileNotFoundError(f"Recording not found:\n{wav}")

    exe = find_audacity_exe()
    if not exe:
        raise FileNotFoundError(
            "Audacity not found.\n\n"
            "Install from https://www.audacityteam.org/\n"
            "or set AUDACITY_EXE to your Audacity.exe path."
        )

    subprocess.Popen([str(exe), str(wav)], close_fds=True)
    return exe
