$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $here

Push-Location $here
try {
    Write-Host "Building Drummer executable (onedir, no UPX - reliable python313.dll loading)..."
    python -m PyInstaller `
        --noconfirm `
        --onedir `
        --noupx `
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
        --hidden-import groove_matcher `
        --hidden-import groove_bpm_cache `
        --hidden-import match_catalog `
        --hidden-import midi_drum_map `
        --hidden-import mido_compat `
        --hidden-import tkinterdnd2 `
        drummer_app.py

    $builtDir = Join-Path $here "dist\Drummer"
    $builtExe = Join-Path $builtDir "Drummer.exe"
    if (-not (Test-Path $builtExe)) {
        throw "Build failed - executable not found at $builtExe"
    }

    foreach ($folder in @("Windows 10", "Windows 11")) {
        $destDir = Join-Path $root $folder
        New-Item -ItemType Directory -Force -Path $destDir | Out-Null
        Get-ChildItem -Path $destDir -Filter "Drummer Studio *.exe" -ErrorAction SilentlyContinue | Remove-Item -Force
        # Merge fresh build into ship folder (handles locked/open target dirs on Windows 11).
        Get-ChildItem -Path $builtDir -Force | ForEach-Object {
            $target = Join-Path $destDir $_.Name
            if ($_.PSIsContainer) {
                if (Test-Path $target) { Remove-Item -Recurse -Force $target -ErrorAction SilentlyContinue }
                Copy-Item -Recurse -Force $_.FullName $target
            } else {
                Copy-Item -Force $_.FullName $target
            }
        }
        $shipExe = Join-Path $destDir "Drummer.exe"
        $finalExe = Join-Path $destDir "Drummer Studio.exe"
        if (Test-Path $shipExe) {
            if (Test-Path $finalExe) { Remove-Item -Force $finalExe -ErrorAction SilentlyContinue }
            Rename-Item -Path $shipExe -NewName "Drummer Studio.exe" -Force
        }
        Write-Host "Copied app folder to $destDir (launch $finalExe)"
    }
}
finally {
    Pop-Location
}

Write-Host "Done."
