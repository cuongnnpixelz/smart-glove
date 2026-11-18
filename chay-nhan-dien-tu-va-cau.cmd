@echo off
cd /d "%~dp0"
"%~dp0.bridge-venv\Scripts\python.exe" -u "%~dp0SmartSignLanguage\predict_phrase_5.py" --serial-port COM3 --user-id U02 --combine-words --recalibrate %*
pause
