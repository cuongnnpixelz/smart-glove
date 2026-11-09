$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

& "$PSScriptRoot\.bridge-venv\Scripts\python.exe" `
  "$PSScriptRoot\SmartSignLanguage\collect_sequence_5.py" `
  --user-id U01 `
  --esp32-host 192.168.137.115 `
  --labels A B C D NONE `
  --repetitions 10

Write-Host ""
Read-Host "Chuong trinh da dung. Nhan Enter de dong cua so"
