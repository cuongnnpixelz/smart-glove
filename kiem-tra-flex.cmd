@echo off
cd /d "%~dp0"
"%~dp0.bridge-venv\Scripts\python.exe" "%~dp0SmartSignLanguage\check_flex_repeatability.py" --serial-port COM3 %*
pause
