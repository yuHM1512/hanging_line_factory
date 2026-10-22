# Hanging Conveyor Dashboard - Dev launcher
# Usage: .\run.ps1            -> chay server tai http://127.0.0.1:8016
#        .\run.ps1 -Setup     -> tao venv va cai requirements
#        .\run.ps1 -CreateDb  -> smoke-test connect + CREATE hanging_app (khong migrate)
#        .\run.ps1 -Migrate   -> ensure hanging_app + apply tat ca SQL migration
#        .\run.ps1 -Reload    -> bat auto-reload khi can debug

param(
    [switch]$Setup,
    [switch]$CreateDb,
    [switch]$Migrate,
    [switch]$Reload,
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8016
)

$CanonicalPort = 8016

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

$venv = Join-Path $PSScriptRoot ".venv"
$py = Join-Path $venv "Scripts\python.exe"

if ($Port -ne $CanonicalPort) {
    throw "Project nay chi duoc chay tren cong $CanonicalPort. Hay dung .\\run.ps1 hoac set -Port $CanonicalPort."
}

if ($Setup -or -not (Test-Path $py)) {
    Write-Host ">> Tao virtualenv .venv ..." -ForegroundColor Cyan
    python -m venv .venv
    & $py -m pip install --upgrade pip
    & $py -m pip install -r requirements.txt
}

if ($CreateDb) {
    Write-Host ">> Smoke-test + CREATE app database ..." -ForegroundColor Cyan
    & $py "scripts/create_app_db.py"
    if ($LASTEXITCODE -ne 0) {
        throw "Create app DB failed (exit $LASTEXITCODE)."
    }
    exit 0
}

if ($Migrate) {
    Write-Host ">> Apply SQL migrations ..." -ForegroundColor Cyan
    & $py "scripts/apply_migrations.py"
    if ($LASTEXITCODE -ne 0) {
        throw "Migration failed (exit $LASTEXITCODE)."
    }
    exit 0
}

$listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique
foreach ($procId in $listeners) {
    if ($procId) {
        Write-Host ">> Stop process dang chiem port ${Port}: PID $procId" -ForegroundColor Yellow
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        if (Test-Path "$env:SystemRoot\System32\taskkill.exe") {
            try {
                cmd /c """$env:SystemRoot\System32\taskkill.exe"" /PID $procId /T /F >nul 2>nul" | Out-Null
            } catch {
                # Ignore "process not found" races here; the definitive check is the port probe below.
            }
        }
    }
}

# Ngay sau khi may reboot bat thuong, Windows doi khi giu port o trang thai "stale"
# (khong con listener nhung van tu choi bind) trong vai giay. Thu lai vai lan thay vi
# throw ngay, vi day chinh la nguyen nhan gay mat auto-start sang 2026-08-26.
$portFree = $false
for ($i = 1; $i -le 5; $i++) {
    Start-Sleep -Seconds 1
    $remaining = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
    if (-not $remaining) {
        $portFree = $true
        break
    }
    Write-Host ">> Port $Port van bi chiem (lan cho $i/5), thu lai..." -ForegroundColor Yellow
}
if (-not $portFree) {
    $pidList = ($remaining | ForEach-Object { $_.ToString() }) -join ", "
    throw "Port $Port van dang bi chiem boi PID: $pidList sau 5 lan cho. Neu taskkill/Stop-Process khong thay PID nay, day la stale listener cua Windows sau uvicorn --reload; reboot Windows la cach nhanh nhat de giai phong port nay."
}

$uvicornArgs = @("-m", "uvicorn", "app.main:app", "--host", $BindHost, "--port", $Port)
if ($Reload) {
    $uvicornArgs += "--reload"
}

$mode = if ($Reload) { "reload" } else { "stable" }

# Uvicorn chay foreground va block cho toi khi server dung. Neu no thoat gan nhu ngay
# lap tuc voi loi (vi du bind that bai do port van con stale), thu lai vai lan truoc
# khi bo cuoc, va luon ghi ro exit code de log khong con "im lang" nhu truoc.
$maxAttempts = 3
$success = $false
for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
    Write-Host ">> Khoi dong Uvicorn tai http://${BindHost}:${Port} ($mode mode) - lan $attempt/$maxAttempts" -ForegroundColor Green
    $startedAt = Get-Date
    & $py @uvicornArgs
    $exitCode = $LASTEXITCODE
    $ranForSeconds = ((Get-Date) - $startedAt).TotalSeconds
    Write-Host ">> Uvicorn da thoat (exit code $exitCode, chay duoc $([math]::Round($ranForSeconds,1))s)" -ForegroundColor Yellow

    if ($exitCode -eq 0) {
        $success = $true
        break
    }
    if ($ranForSeconds -ge 10) {
        # Server da chay on dinh mot thoi gian roi moi thoat (vi du bi kill thu cong) -> khong retry.
        $success = $true
        break
    }
    if ($attempt -lt $maxAttempts) {
        Write-Host ">> Uvicorn thoat qua nhanh, cho 5s roi thu lai..." -ForegroundColor Red
        Start-Sleep -Seconds 5
    }
}
if (-not $success) {
    throw "Uvicorn khong khoi dong duoc sau $maxAttempts lan thu (exit code cuoi: $exitCode)."
}
