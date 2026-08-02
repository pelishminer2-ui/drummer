$ErrorActionPreference = "Stop"
$AppName = "Drummer Studio"
$InstallDir = Join-Path $env:LOCALAPPDATA "Programs\Drummer Studio"
$SourceExe = Join-Path $PSScriptRoot "source\dist\Drummer.exe"
$Desktop = [Environment]::GetFolderPath("Desktop")
$StartMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"

if (-not (Test-Path $SourceExe)) {
    Write-Host "Building application first..."
    & (Join-Path $PSScriptRoot "source\build_installer.ps1")
    $SourceExe = Join-Path $PSScriptRoot "source\dist\Drummer.exe"
}

if (-not (Test-Path $SourceExe)) {
    throw "Drummer.exe not found. Run source\build_installer.ps1 first."
}

Write-Host "Installing $AppName to $InstallDir"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item -Force $SourceExe (Join-Path $InstallDir "Drummer Studio.exe")
foreach ($doc in @("Read Me.txt", "LICENSE", "README.md", "CONTRIBUTING.md")) {
    $src = Join-Path $PSScriptRoot $doc
    if (Test-Path $src) {
        Copy-Item -Force $src (Join-Path $InstallDir $doc)
    }
}

$WshShell = New-Object -ComObject WScript.Shell

$DesktopLink = Join-Path $Desktop "$AppName.lnk"
$Shortcut = $WshShell.CreateShortcut($DesktopLink)
$Shortcut.TargetPath = Join-Path $InstallDir "Drummer Studio.exe"
$Shortcut.WorkingDirectory = $InstallDir
$Shortcut.Description = "Drummer Studio - custom drum engine"
$Shortcut.Save()

$StartLink = Join-Path $StartMenu "$AppName.lnk"
$Shortcut2 = $WshShell.CreateShortcut($StartLink)
$Shortcut2.TargetPath = Join-Path $InstallDir "Drummer Studio.exe"
$Shortcut2.WorkingDirectory = $InstallDir
$Shortcut2.Save()

Write-Host ""
Write-Host "Installation complete!"
Write-Host "  $InstallDir"
Write-Host "  Desktop shortcut created"
Write-Host "  Start Menu shortcut created"
Write-Host ""
Write-Host "Launch: Drummer Studio from Desktop or Start Menu"
Write-Host ""
Write-Host "Libraries: $PSScriptRoot\Libraries"
Write-Host "First-time: run Import-Libraries.ps1 to import samples"
