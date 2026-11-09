@echo off
cd /d "%~dp0"
"%~dp0.bridge-venv\Scripts\python.exe" "%~dp0SmartSignLanguage\collect_sequence_com.py" --serial-port COM3 --user-id U01 --gesture-type auto --labels E F G H I J K L M N O P Q R S T U V W X Y Z NONE --repetitions 10 %*
pause
