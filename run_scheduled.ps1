$ErrorActionPreference = "Stop"
Set-Location -Path "D:\hanging_line_factory"

$logDir = "D:\hanging_line_factory\logs"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}
$logFile = Join-Path $logDir ("run_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

Start-Transcript -Path $logFile -Append

try {
    & ".\.venv\Scripts\Activate.ps1"
    & ".\run.ps1"
}
finally {
    Stop-Transcript
}
