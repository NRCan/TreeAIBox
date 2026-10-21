# Launch LAS to LAZ Converter
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host "Starting LAS to LAZ Converter in virtual environment (.venv)..." -ForegroundColor Cyan
& "$scriptDir\.venv\Scripts\python.exe" "$scriptDir\scripts\pointcloud_processing\las_to_laz.py" $args
