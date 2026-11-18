@echo off
cd /d "%~dp0"
"%~dp0.bridge-venv\Scripts\python.exe" -X utf8 "%~dp0SmartSignLanguage\collect_phrase_5.py" --serial-port COM3 --user-id U02 %*
pause
