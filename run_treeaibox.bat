@echo off
setlocal
cd /d "%~dp0"
echo Starting TreeAIBox Standalone with CUDA acceleration...
call .venv\Scripts\activate.bat
python TreeAIBox.py
pause
