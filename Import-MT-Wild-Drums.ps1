# Import MT Power Drum Kit (MT Wild Drums) from Downloads into F:\Drummer\Libraries\MT-Wild-Drums.
# Safe to re-run - skips extraction if plugin files already exist.

$ErrorActionPreference = "Stop"
$Root = "F:\Drummer"
$LibRoot = Join-Path $Root "Libraries"
$Dest = Join-Path $LibRoot "MT-Wild-Drums"
$SourceDir = "C:\Users\Owner\Downloads\New folder (2)"
$7z = "C:\Program Files\7-Zip\7z.exe"

Write-Host "Drummer Studio - MT Wild Drums import" -ForegroundColor Cyan
Write-Host "Target: $Dest"

New-Item -ItemType Directory -Force -Path $Dest | Out-Null

$zip = Get-ChildItem -LiteralPath $SourceDir -Filter "*.zip" -File -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $zip) {
    throw "No zip found in $SourceDir"
}

$marker = Join-Path $Dest "MT-PowerDrumKit.vst3"
if (-not (Test-Path $marker)) {
    if (-not (Test-Path $7z)) {
        throw "7-Zip required at $7z"
    }
    Write-Host "Extracting $($zip.Name) ..."
    & $7z x $zip.FullName "-o$Dest" -y | Out-Null
    if ($LASTEXITCODE -gt 1) {
        throw "7-Zip extract failed ($LASTEXITCODE)"
    }
    Get-ChildItem $Dest -Directory | ForEach-Object {
        Get-ChildItem $_.FullName -File | ForEach-Object {
            Move-Item -Force $_.FullName (Join-Path $Dest $_.Name)
        }
        Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
    }
    Write-Host "OK: extracted VST3 + content pack" -ForegroundColor Green
} else {
    Write-Host "OK: MT Wild Drums already installed" -ForegroundColor Green
}

Get-ChildItem $Dest -File | ForEach-Object { Write-Host "  $($_.Name)" }
Write-Host "Extracting playable WAV samples from .pdk ..."
python (Join-Path $Root "source\pdk_parser.py") $Dest
if ($LASTEXITCODE -ne 0) { throw "PDK sample extraction failed ($LASTEXITCODE)" }
Write-Host "Select MT Wild Drums in Drummer Studio — kit is now playable in-app." -ForegroundColor Cyan
