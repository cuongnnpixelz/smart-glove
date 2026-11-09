$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

& "$PSScriptRoot\.bridge-venv\Scripts\python.exe" `
  "$PSScriptRoot\SmartSignLanguage\train_sequence_5.py"

Write-Host ""
Read-Host "Chuong trinh da dung. Nhan Enter de dong cua so"
