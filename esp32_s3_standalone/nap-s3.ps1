param(
    [string]$Port,
    [switch]$CompileOnly,
    [switch]$NativeUsb
)
$ErrorActionPreference = 'Stop'
$gloveCli = Get-Command arduino-cli -ErrorAction SilentlyContinue
$gloveCliPath = if ($gloveCli) { $gloveCli.Source } else { 'C:\Program Files\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe' }
if (-not (Test-Path -LiteralPath $gloveCliPath)) { throw 'Can cai Arduino IDE/arduino-cli va core esp32.' }
if (-not $CompileOnly -and [string]::IsNullOrWhiteSpace($Port)) { throw 'Chi ro -Port COMx cua ESP32-S3, hoac -CompileOnly.' }
$gloveSketch = Join-Path $PSScriptRoot 'firmware'
$gloveBuild = Join-Path $PSScriptRoot '..\.firmware-s3-standalone-build'
$gloveCdc = if ($NativeUsb) { 'cdc' } else { 'default' }
$gloveBoard = "esp32:esp32:esp32s3:FlashSize=16M,PSRAM=opi,PartitionScheme=app3M_fat9M_16MB,USBMode=hwcdc,CDCOnBoot=$gloveCdc,UploadSpeed=115200"
Write-Host 'Bien dich ESP32-S3 N16R8, Flash 16MB, OPI PSRAM. Core da kiem tra: 2.0.14.'
& $gloveCliPath compile --fqbn $gloveBoard --build-path $gloveBuild $gloveSketch
if ($LASTEXITCODE -ne 0) { throw 'Bien dich that bai; chua nap.' }
if ($CompileOnly) { Write-Host 'BIEN DICH XONG; chua nap chip.'; exit 0 }
Write-Host "Dong Python/Serial Monitor tren $Port. Dang nap ESP32-S3 o 115200 baud..."
& $gloveCliPath upload --port $Port --fqbn $gloveBoard --input-dir $gloveBuild $gloveSketch
if ($LASTEXITCODE -ne 0) { throw 'Nap that bai. Kiem tra COM/cap USB; thu giu BOOT, bam RESET, tha BOOT.' }
Write-Host 'DA NAP. Mo Serial Monitor 115200 baud, Newline. Khong chay Python predict_* cung COM.'
