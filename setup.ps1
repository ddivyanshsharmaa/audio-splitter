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

$up = $WshShell.CreateShortcut("$env:USERPROFILE\Desktop\Audio Delay Increase.lnk")
$up.TargetPath = "$here\venv\Scripts\pythonw.exe"
$up.Arguments = "`"$here\adjust_delay.pyw`" +"
$up.WorkingDirectory = $here
$up.Hotkey = "CTRL+ALT+O"
$up.Description = "Increase aux delay by 10ms (sync aux later, closer to Bluetooth)"
$up.Save()

$down = $WshShell.CreateShortcut("$env:USERPROFILE\Desktop\Audio Delay Decrease.lnk")
$down.TargetPath = "$here\venv\Scripts\pythonw.exe"
$down.Arguments = "`"$here\adjust_delay.pyw`" -"
$down.WorkingDirectory = $here
$down.Hotkey = "CTRL+ALT+P"
$down.Description = "Decrease aux delay by 10ms (sync aux earlier)"
$down.Save()

Write-Host ""
Write-Host "Done. Before first use:" -ForegroundColor Green
Write-Host "  1. Run: .\venv\Scripts\python.exe .\list_devices.py"
Write-Host "  2. Edit config.py with your own device names from that list"
Write-Host "  3. Press Ctrl+Alt+B to turn it on"
