@echo off
cd /d "%~dp0"
"%~dp0.bridge-venv\Scripts\python.exe" -X utf8 "%~dp0SmartSignLanguage\collect_sequence_com.py" --serial-port COM3 --user-id U01 --interactive-labels --repetitions 10 %*
pause
