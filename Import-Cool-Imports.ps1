# Import WAV / MP3 / MIDI into Libraries\Cool-Imports (not XLN .xpak files).
param(
    [string]$Source = ""
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$SourceDir = Join-Path $Root "source"
$Inbox = Join-Path $Root "Libraries\Cool-Imports\Inbox"

if (-not $Source) {
    $Source = $Inbox
}

Write-Host "Cool Imports — copy audio into Drummer Studio" -ForegroundColor Cyan
Write-Host "Source: $Source"
Write-Host ""

Push-Location $SourceDir
try {
    python cool_imports_import.py $Source
    if ($LASTEXITCODE -ne 0) { throw "cool_imports_import.py failed" }
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "In Drummer Studio: Library -> Cool Imports" -ForegroundColor Green
Write-Host "Tip: drop WAV/MIDI in Libraries\Cool-Imports\Inbox and re-run this script." -ForegroundColor DarkGray
