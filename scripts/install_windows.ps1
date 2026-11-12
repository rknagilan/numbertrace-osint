# NumberTrace OSINT installer for Windows 11 (PowerShell). Run from the project folder:
#   powershell -ExecutionPolicy Bypass -File scripts\install_windows.ps1 [-Web] [-Dev]
param([switch]$Web, [switch]$Dev)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$py = Get-Command py -ErrorAction SilentlyContinue
if (-not $py) { Write-Host "Python launcher 'py' not found. Install Python 3.12+ from python.org (tick 'Add to PATH')."; exit 1 }
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)"
if ($LASTEXITCODE -ne 0) { Write-Host "Python 3.12+ is required."; exit 1 }
if (-not (Test-Path .venv)) { py -3 -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
$extra = ""
if ($Web) { $extra = "[web]" }
if ($Dev) { $extra = "[dev]" }
& .\.venv\Scripts\pip.exe install --quiet -e ".$extra"
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
Write-Host "Done. Next:  .\.venv\Scripts\Activate.ps1 ; numbertrace doctor ; numbertrace demo"
