$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

& "$PSScriptRoot\.bridge-venv\Scripts\python.exe" `
  "$PSScriptRoot\SmartSignLanguage\predict_continuous.py" `
  --esp32-host 192.168.137.115

Write-Host ""
Read-Host "Chuong trinh da dung. Nhan Enter de dong cua so"
