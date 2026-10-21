@echo off
setlocal
cd /d "%~dp0"
echo Running Automated Tree Segmentation Refiner...
call .venv\Scripts\activate.bat
python scripts\pointcloud_processing\refine_segmented_plots.py
pause
