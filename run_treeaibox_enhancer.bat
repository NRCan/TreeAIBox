@echo off
setlocal
cd /d "%~dp0"
echo Starting TreeAIBox Enhancer...
call .venv\Scripts\activate.bat
python scripts\visualization\treeAIbox_Enhancer.py
pause
