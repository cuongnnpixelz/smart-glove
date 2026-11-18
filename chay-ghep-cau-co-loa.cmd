@echo off
cd /d "%~dp0"
python -m SmartSignLanguage.predict_sentence_words --serial-port COM3 --min-votes 5 --none-windows 10 --speak %*
pause
