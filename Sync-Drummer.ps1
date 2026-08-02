# Sync metadata + rebuild Drummer Studio for F:\Drummer
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Source = Join-Path $Root "source"

Write-Host "Drummer Studio - full sync and rebuild" -ForegroundColor Cyan
Write-Host "Root: $Root"
Write-Host ""

# 1) Read app version from source
$AppPy = Join-Path $Source "drummer_app.py"
$Version = "unknown"
if (Test-Path $AppPy) {
    $content = Get-Content $AppPy -Raw
    if ($content -match 'APP_VERSION = "([0-9.]+)"') {
        $Version = $Matches[1]
    }
}
Write-Host "App version: $Version" -ForegroundColor Green

# 2) Sync Libraries\manifest.json from disk scan
Write-Host ""
Write-Host "Syncing Libraries\manifest.json ..."
Push-Location $Source
try {
    python sync_manifest.py
    if ($LASTEXITCODE -ne 0) { throw "sync_manifest.py failed" }
}
finally {
    Pop-Location
}

# 3) Update Read Me.txt version stamp
$ReadMe = Join-Path $Root "Read Me.txt"
if (Test-Path $ReadMe) {
    $text = Get-Content $ReadMe -Raw
    if ($text -match "Version: [0-9.]+") {
        $text = $text -replace "Version: [0-9.]+", "Version: $Version"
    } else {
        $text = "Version: $Version`r`n`r`n" + $text
    }
    [System.IO.File]::WriteAllText($ReadMe, $text.TrimEnd() + "`r`n")
    Write-Host "Updated Read Me.txt" -ForegroundColor Green
}

# 4) Rebuild executable
Write-Host ""
Write-Host "Building executable ..."
& (Join-Path $Source "build_installer.ps1")
if ($LASTEXITCODE -ne 0) { throw "build_installer.ps1 failed" }

$Win10 = Join-Path $Root "Windows 10\Drummer Studio.exe"
$Win11 = Join-Path $Root "Windows 11\Drummer Studio.exe"

foreach ($dest in @($Win10, $Win11)) {
    if (Test-Path $dest) {
        $info = Get-Item $dest
        $sizeMb = [math]::Round($info.Length / 1MB, 1)
        Write-Host "Shipped: $dest (${sizeMb} MB)" -ForegroundColor Green
    }
}

# 5) Write build stamp
$Stamp = Join-Path $Root "BUILD.txt"
$BuiltAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$stampLines = @(
    "Drummer Studio build stamp",
    "==========================",
    "Version:     $Version",
    "Built:       $BuiltAt",
    "Manifest:    Libraries\manifest.json (schema synced)",
    "Executables:",
    "  Windows 10\Drummer Studio.exe (+ _internal folder)",
    "  Windows 11\Drummer Studio.exe (+ _internal folder)",
    "  source\dist\Drummer\Drummer.exe"
)
$stampLines | Set-Content -Path $Stamp -Encoding UTF8

Write-Host ""
Write-Host "Done. Launch: $Win11" -ForegroundColor Cyan
