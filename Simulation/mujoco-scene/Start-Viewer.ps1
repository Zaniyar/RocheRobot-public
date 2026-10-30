# Startet den MuJoCo-Viewer (Windows PowerShell 5.1 kompatibel, kein '&&').
#   .\Start-Viewer.ps1            -> Demonstrator greift das Kit wiederholt
#   .\Start-Viewer.ps1 -Free      -> freie Szene, Gelenke per Schieberegler
param([switch]$Free)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$py = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) {
    Write-Host 'Erstelle .venv und installiere Abhaengigkeiten ...'
    python -m venv .venv
    & $py -m pip install -r requirements.txt
}
if ($Free) { & $py view_scene.py } else { & $py view_scene.py --demo }
