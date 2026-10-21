# Run Automated Tree Segmentation Refiner
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host "Running Automated Tree Segmentation Refiner (.venv)..." -ForegroundColor Cyan
& "$scriptDir\.venv\Scripts\python.exe" "$scriptDir\scripts\pointcloud_processing\refine_segmented_plots.py"
