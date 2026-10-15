<#
.SYNOPSIS
  One-command local setup for the API Key lab on Windows. No admin rights needed.

.DESCRIPTION
  Safe to re-run: every step checks first and skips what is already done.

    1. .env files + docker compose up        Postgres only (needs Docker Desktop); no Keycloak
    2. backend .venv + requirements.txt      then `alembic upgrade head` (tables + two seeded demo keys)
    3. frontend npm install
    4. start FastAPI (:8004) and Vite (:5177) in this terminal, open the browser; Ctrl+C stops both

  Ports differ from the other labs, so they can all run at the same time.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\setup-local-dev.ps1
#>

$Backend  = Split-Path $PSScriptRoot -Parent
$Lab      = Split-Path $Backend -Parent
$Frontend = Join-Path $Lab "frontend"
$Compose  = Join-Path $Lab "docker-compose.yml"

$ApiPort = 8004
$WebPort = 5177

function Step($Message) { Write-Host "`n==> $Message" -ForegroundColor Cyan }
function Skip($Message) { Write-Host "    already done: $Message" -ForegroundColor DarkGray }
function Done($Message) { Write-Host "    $Message" -ForegroundColor Green }

function Exec([string]$What, [scriptblock]$Command) {
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$What failed (exit code $LASTEXITCODE)" }
}

function Test-Port([int]$Port) {
    [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

if ($MyInvocation.InvocationName -eq '.') { return }

$started = @()
try {
    Step "1. Docker: Postgres"
    foreach ($dir in $Lab, $Backend) {
        if (Test-Path "$dir\.env") { Skip "$dir\.env" }
        else { Copy-Item "$dir\.env.example" "$dir\.env" -ErrorAction Stop; Done "created $dir\.env from .env.example" }
    }
    cmd /c "docker info >nul 2>&1"
    if ($LASTEXITCODE -ne 0) { throw "Docker is not running. Start Docker Desktop, then re-run this script." }
    Exec "docker compose up" { docker compose -f $Compose up -d }

    Step "2. Backend Python environment ($Backend\.venv)"
    $VenvPython = "$Backend\.venv\Scripts\python.exe"
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        if (-not (Test-Path $VenvPython)) { Exec "uv venv" { uv venv --python 3.12 "$Backend\.venv" } }
        Exec "uv pip install" { uv pip install --link-mode=copy --python $VenvPython -r "$Backend\requirements.txt" }
    } else {
        if (-not (Test-Path $VenvPython)) { Exec "python venv" { py -3.12 -m venv "$Backend\.venv" } }
        Exec "pip install" { & $VenvPython -m pip install -r "$Backend\requirements.txt" }
    }
    Done "backend dependencies installed"
    # Creates the tables and seeds the two demo keys (retries while Postgres finishes starting).
    Push-Location $Backend
    try {
        $ok = $false
        foreach ($i in 1..15) { & "$Backend\.venv\Scripts\alembic.exe" upgrade head; if ($LASTEXITCODE -eq 0) { $ok = $true; break }; Start-Sleep 2 }
        if (-not $ok) { throw "alembic upgrade head failed (is Postgres up on :5438?)" }
    } finally { Pop-Location }
    Done "database tables + seeded demo keys up to date (alembic)"

    Step "3. Frontend packages"
    Push-Location $Frontend
    try { Exec "npm install" { npm install --no-fund --no-audit } } finally { Pop-Location }
    Done "frontend dependencies installed"

    Step "4. Start FastAPI and the frontend in this terminal"
    if (Test-Port $ApiPort) { Skip "something already listens on :$ApiPort" }
    else {
        $started += Start-Process "$Backend\.venv\Scripts\fastapi.exe" -ArgumentList "dev", "app/main.py", "--port", "$ApiPort" `
            -WorkingDirectory $Backend -NoNewWindow -PassThru
        Done "FastAPI starting -> http://localhost:$ApiPort/docs"
    }
    if (Test-Port $WebPort) { Skip "something already listens on :$WebPort" }
    else {
        $started += Start-Process node -ArgumentList "node_modules\vite\bin\vite.js" `
            -WorkingDirectory $Frontend -NoNewWindow -PassThru
        Done "Vite starting -> http://localhost:$WebPort"
    }
    $deadline = (Get-Date).AddSeconds(30)
    while (-not ((Test-Port $WebPort) -and (Test-Port $ApiPort)) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 1 }
    Start-Process "http://localhost:$WebPort"

    Write-Host "`nAll set. Open http://localhost:$WebPort and sign in with the seeded key:" -ForegroundColor Green
    Write-Host "  mial_live_demo_do_not_use_in_prod" -ForegroundColor Green

    if ($started) {
        Write-Host "`nFastAPI and Vite logs follow below. Press Ctrl+C to stop both.`n" -ForegroundColor Yellow
        Wait-Process -Id $started.Id
    }
}
catch {
    Write-Host "`nFAILED: $_" -ForegroundColor Red
    exit 1
}
finally {
    foreach ($p in $started) { taskkill /T /F /PID $p.Id *> $null }
}
