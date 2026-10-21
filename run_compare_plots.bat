@echo off
setlocal
cd /d "%~dp0"
echo Starting Side-by-Side 3D Plot Comparison GUI...
call .venv\Scripts\activate.bat
python scripts\visualization\compare_segmentation_gui.py
pause
