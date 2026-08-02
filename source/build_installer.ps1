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
        --hidden-import PIL.Image `
        --hidden-import PIL.ImageTk `
        --hidden-import pygame.sndarray `
        --hidden-import audio_prep `
        --hidden-import groove_render `
        --hidden-import midi_drum_map `
        drummer_app.py

    $built = Join-Path $here "dist\Drummer.exe"
    if (-not (Test-Path $built)) {
        throw "Build failed - executable not found."
    }

    foreach ($folder in @("Windows 10", "Windows 11")) {
        $destDir = Join-Path $root $folder
        New-Item -ItemType Directory -Force -Path $destDir | Out-Null
        $dest = Join-Path $destDir "Drummer Studio.exe"
        Copy-Item -Force $built $dest
        Write-Host "Copied installer to $dest"
    }
}
finally {
    Pop-Location
}

Write-Host "Done."
