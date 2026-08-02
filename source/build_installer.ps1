$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $here

Push-Location $here
try {
    Write-Host "Building Drummer executable..."
    python -m PyInstaller `
        --noconfirm `
        --onefile `
        --windowed `
        --name "Drummer" `
        --add-data "..\LICENSE;." `
        --add-data "assets;assets" `
        --collect-all tkinterdnd2 `
        --hidden-import PIL.Image `
        --hidden-import PIL.ImageTk `
        --hidden-import pygame.sndarray `
        --hidden-import audio_prep `
        --hidden-import groove_render `
        --hidden-import midi_drum_map `
        --hidden-import tkinterdnd2 `
        drummer_app.py

    $built = Join-Path $here "dist\Drummer.exe"
    if (-not (Test-Path $built)) {
        throw "Build failed - executable not found."
    }

    foreach ($folder in @("Windows 10", "Windows 11")) {
        $destDir = Join-Path $root $folder
        New-Item -ItemType Directory -Force -Path $destDir | Out-Null
        # Drop leftover versioned builds (e.g. Drummer Studio 2.5.0.exe) — only one portable exe ships.
        Get-ChildItem -Path $destDir -Filter "Drummer Studio *.exe" -ErrorAction SilentlyContinue | Remove-Item -Force
        $dest = Join-Path $destDir "Drummer Studio.exe"
        Copy-Item -Force $built $dest
        Write-Host "Copied installer to $dest"
    }
}
finally {
    Pop-Location
}

Write-Host "Done."
