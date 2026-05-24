param(
    [switch]$CleanOnly
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Get-Process DanbooruManager -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Remove-Item .\build -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item .\dist -Recurse -Force -ErrorAction SilentlyContinue

if ($CleanOnly) {
    exit 0
}

.\.venv\Scripts\python.exe -m PyInstaller .\DanbooruManager.spec --clean
