@echo off
cd /d "%~dp0"
"%~dp0.bridge-venv\Scripts\python.exe" -u "%~dp0SmartSignLanguage\train_phrase_5.py" --train-all %*
pause
