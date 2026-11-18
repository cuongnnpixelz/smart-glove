param([string]$Port = 'COM3')
$ErrorActionPreference = 'Stop'
$gloveCli = Get-Command arduino-cli -ErrorAction SilentlyContinue
if ($gloveCli) {
    $gloveCliPath = $gloveCli.Source
} else {
    $gloveCliPath = 'C:\Program Files\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe'
}
if (-not (Test-Path -LiteralPath $gloveCliPath)) {
    throw 'Khong tim thay arduino-cli. Mo mophong_com/mophong_com.ino bang Arduino IDE de nap.'
}
$gloveSketch = Join-Path $PSScriptRoot 'mophong_com'
$gloveBuild = Join-Path $PSScriptRoot '.firmware-com-audio-build'
Write-Host 'Dong chuong trinh Python/Serial Monitor dang dung COM truoc khi nap.'
& $gloveCliPath compile --fqbn esp32:esp32:esp32 --build-path $gloveBuild $gloveSketch
if ($LASTEXITCODE -ne 0) { throw 'Bien dich that bai; chua nap ESP32.' }
& $gloveCliPath upload --port $Port --fqbn esp32:esp32:esp32 --input-dir $gloveBuild $gloveSketch
if ($LASTEXITCODE -ne 0) { throw 'Nap that bai. Kiem tra COM/cap USB; giu BOOT neu bo mach yeu cau.' }
Write-Host 'DA NAP. Test: python -m SmartSignLanguage.esp32_speech --serial-port' $Port
