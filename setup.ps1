<#
Sets up audio-splitter: creates a venv, installs Python + PowerShell
dependencies, and creates the desktop shortcuts with hotkeys.

Run this from an ordinary PowerShell prompt (no admin needed):
    .\setup.ps1

It creates config.py from config.example.py if you don't have one yet.
Edit config.py afterwards so the three device names match YOUR OWN aux
output, Bluetooth speaker, and a silent virtual audio device on your
machine (see README.md for how to find one).
#>

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

if (-not (Test-Path ".\config.py")) {
    Write-Host "Creating config.py from config.example.py..." -ForegroundColor Cyan
    Copy-Item ".\config.example.py" ".\config.py"
}

Write-Host "Creating virtual environment..." -ForegroundColor Cyan
python -m venv venv

Write-Host "Installing Python dependencies..." -ForegroundColor Cyan
& ".\venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\venv\Scripts\python.exe" -m pip install -r requirements.txt

Write-Host "Installing AudioDeviceCmdlets (PowerShell module for switching/volume)..." -ForegroundColor Cyan
Install-PackageProvider -Name NuGet -MinimumVersion 2.8.5.201 -Force -Scope CurrentUser | Out-Null
Set-PSRepository -Name PSGallery -InstallationPolicy Trusted
Install-Module -Name AudioDeviceCmdlets -Scope CurrentUser -Force -Confirm:$false

Write-Host "Creating desktop shortcuts with hotkeys..." -ForegroundColor Cyan
$WshShell = New-Object -ComObject WScript.Shell

$toggle = $WshShell.CreateShortcut("$env:USERPROFILE\Desktop\Audio Splitter Toggle.lnk")
$toggle.TargetPath = "$here\venv\Scripts\pythonw.exe"
$toggle.Arguments = "`"$here\toggle.pyw`""
$toggle.WorkingDirectory = $here
$toggle.Hotkey = "CTRL+ALT+B"
$toggle.Description = "Toggle mirroring aux speaker audio to Bluetooth speaker"
$toggle.Save()

$app = $WshShell.CreateShortcut("$env:USERPROFILE\Desktop\Audio Splitter.lnk")
$app.TargetPath = "$here\venv\Scripts\pythonw.exe"
$app.Arguments = "`"$here\app.pyw`""
$app.WorkingDirectory = $here
$app.IconLocation = "C:\Windows\System32\SndVol.exe,0"
$app.Hotkey = "CTRL+ALT+K"
$app.Description = "Audio Splitter control panel - per-device latency and volume"
$app.Save()

# Shortcuts from earlier versions, if present.
Remove-Item "$env:USERPROFILE\Desktop\Audio Delay Increase.lnk" -ErrorAction SilentlyContinue
Remove-Item "$env:USERPROFILE\Desktop\Audio Delay Decrease.lnk" -ErrorAction SilentlyContinue
Remove-Item "$env:USERPROFILE\Desktop\Audio Calibrate.lnk" -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Done. Before first use:" -ForegroundColor Green
Write-Host "  1. Run: .\venv\Scripts\python.exe .\list_devices.py"
Write-Host "  2. Edit config.py -- list every speaker you want in OUTPUTS"
Write-Host "  3. Run: .\venv\Scripts\python.exe .\device_check.py  (confirm each is audible)"
Write-Host "  4. Press Ctrl+Alt+K for the app, or Ctrl+Alt+B to toggle on/off"
