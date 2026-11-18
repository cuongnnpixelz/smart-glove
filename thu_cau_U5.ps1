$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
Write-Host 'THU CAU U5: 5 giay/luot, 10 luot/cau.'
Write-Host 'Nhap lan luot: TOI_CAM_ON_BAN, BAN_KHOE_KHONG, TOI_KHOE, BAN_TEN_GI, BAN_DANG_LAM_GI, NONE.'
Write-Host 'Khi hoi thoi gian/so luot: Enter de dung 5 giay / 10 luot.'
Write-Host 'Cho BAT DAU moi lam tron cau mot lan. Enter: luu; R: bo luot sai. /Q: ket thuc.'
python -m SmartSignLanguage.collect_phrase_5 --serial-port COM3 --user-id U5 --seconds 5 --repetitions 10 --output-dir SmartSignLanguage/phrase_data_5_100hz_sentence_trial_20261114
exit $LASTEXITCODE
