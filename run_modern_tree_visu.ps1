# Launch Modern Tree Visualizer GUI
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host "Activating virtual environment (.venv)..." -ForegroundColor Cyan
& "$scriptDir\.venv\Scripts\python.exe" "$scriptDir\scripts\visualization\tree_visu.py"
