param(
    [string]$Port = "COM3",
    [string]$UserId = "U01",
    [string[]]$Labels = @("E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z", "NONE"),
    [int]$Repetitions = 10,
    [switch]$WatchFlex
)
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot ".bridge-venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Khong thay .bridge-venv. Xem docs/thu-qua-com.md de cai moi truong."
}
$collectArgs = @(
    "$PSScriptRoot\SmartSignLanguage\collect_sequence_com.py",
    "--user-id", $UserId, "--repetitions", "$Repetitions", "--gesture-type", "auto", "--labels"
)
$collectArgs += $Labels
if ($Port) { $collectArgs += @("--serial-port", $Port) }
if ($WatchFlex) { $collectArgs += "--watch-flex" }
& $pythonPath @collectArgs
$collectorExit = $LASTEXITCODE
Write-Host ""
Read-Host "Chuong trinh da dung. Nhan Enter de dong cua so"
exit $collectorExit
