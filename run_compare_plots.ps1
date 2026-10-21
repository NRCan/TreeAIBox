# Launch Side-by-Side 3D Plot Comparison GUI
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host "Starting Side-by-Side 3D Plot Comparison GUI (.venv)..." -ForegroundColor Cyan
& "$scriptDir\.venv\Scripts\python.exe" "$scriptDir\scripts\visualization\compare_segmentation_gui.py"
