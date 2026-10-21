# Launch TreeAIBox Enhancer GUI
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir
$env:PYTHONIOENCODING = "utf-8"

Write-Host "Starting TreeAIBox Enhancer in virtual environment (.venv)..." -ForegroundColor Cyan
& "$scriptDir\.venv\Scripts\python.exe" "$scriptDir\scripts\visualization\treeAIbox_Enhancer.py" $args
