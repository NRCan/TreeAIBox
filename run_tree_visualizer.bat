@echo off
setlocal
cd /d "%~dp0"
echo Starting Tree Visualizer GUI...
call .venv\Scripts\activate.bat
python scripts\visualization\tree_visualizer_gui.py
pause
