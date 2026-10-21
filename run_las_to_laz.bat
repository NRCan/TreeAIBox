@echo off
setlocal
cd /d "%~dp0"
echo Starting LAS to LAZ Converter...
call .venv\Scripts\activate.bat
python scripts\pointcloud_processing\las_to_laz.py %*
if "%~1"=="" pause
