@echo off
cd /d "%~dp0"
"%~dp0.bridge-venv\Scripts\python.exe" "%~dp0SmartSignLanguage\predict_continuous_5.py" %*
pause
