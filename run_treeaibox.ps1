# Launch TreeAIBox Standalone with CUDA support
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host "Activating virtual environment (.venv)..." -ForegroundColor Cyan
& "$scriptDir\.venv\Scripts\python.exe" "$scriptDir\TreeAIBox.py"
