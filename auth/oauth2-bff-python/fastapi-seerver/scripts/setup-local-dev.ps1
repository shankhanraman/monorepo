<#
.SYNOPSIS
  One-command local setup for the OAuth 2.0 BFF lab on Windows. No admin rights needed.

.DESCRIPTION
  Safe to re-run: every step checks first and skips what is already done.

    1. .env files + docker compose up        Postgres + Keycloak (needs Docker Desktop)
    2. wait for Keycloak                     realm bff-lab answers at http://localhost:8082
    3. backend .venv + requirements.txt      then `alembic upgrade head` (creates the app's tables)
    4. frontend npm install
    5. start FastAPI (:8002) and Vite (:5175, proxies /api and /auth to FastAPI) in this terminal, open the browser; Ctrl+C stops both

  Ports differ from the keykloak-python project, so both labs can run at the same time.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\setup-local-dev.ps1
#>

$Backend  = Split-Path $PSScriptRoot -Parent
$Lab      = Split-Path $Backend -Parent
$Frontend = Join-Path $Lab "frontend"
$Compose  = Join-Path $Lab "docker-compose.yml"

$KeycloakUrl = "http://localhost:8082"
$Realm       = "bff-lab"
$ApiPort     = 8002
$WebPort     = 5175

function Step($Message) { Write-Host "`n==> $Message" -ForegroundColor Cyan }
function Skip($Message) { Write-Host "    already done: $Message" -ForegroundColor DarkGray }
function Done($Message) { Write-Host "    $Message" -ForegroundColor Green }

# Run a native command and stop the script if it fails.
function Exec([string]$What, [scriptblock]$Command) {
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$What failed (exit code $LASTEXITCODE)" }
}

function Test-Port([int]$Port) {
    [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Test-Url([string]$Url) {
    try { (Invoke-WebRequest $Url -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200 } catch { $false }
}

# Dot-sourcing (. .\setup-local-dev.ps1) only loads the functions, without running the setup.
if ($MyInvocation.InvocationName -eq '.') { return }

$started = @()  # server processes started by step 5, stopped again on exit
try {
    Step "1. Docker: Postgres + Keycloak"
    # First run: create the .env files (passwords, database location) from the committed examples.
    foreach ($dir in $Lab, $Backend) {
        if (Test-Path "$dir\.env") { Skip "$dir\.env" }
        else { Copy-Item "$dir\.env.example" "$dir\.env" -ErrorAction Stop; Done "created $dir\.env from .env.example" }
    }
    cmd /c "docker info >nul 2>&1"
    if ($LASTEXITCODE -ne 0) { throw "Docker is not running. Start Docker Desktop, then re-run this script." }
    # Starts the `db` container only when .env has COMPOSE_PROFILES=local-db (otherwise: installed Postgres / AWS)
    Exec "docker compose up" { docker compose -f $Compose up -d }

    Step "2. Wait for Keycloak (first start imports realm $Realm)"
    $discovery = "$KeycloakUrl/realms/$Realm/.well-known/openid-configuration"
    $deadline = (Get-Date).AddMinutes(3)
    while (-not (Test-Url $discovery) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 3 }
    if (-not (Test-Url $discovery)) { throw "Keycloak not ready at $discovery. Check: docker compose logs keycloak" }
    Done "Keycloak ready at $KeycloakUrl (admin console: admin / admin)"

    Step "3. Backend Python environment ($Backend\.venv)"
    $VenvPython = "$Backend\.venv\Scripts\python.exe"
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        if (-not (Test-Path $VenvPython)) { Exec "uv venv" { uv venv --python 3.12 "$Backend\.venv" } }
        # copy mode: hard-linked installs from uv's cache have come out incomplete on this machine
        Exec "uv pip install" { uv pip install --link-mode=copy --python $VenvPython -r "$Backend\requirements.txt" }
    } else {
        if (-not (Test-Path $VenvPython)) { Exec "python venv" { py -3.12 -m venv "$Backend\.venv" } }
        Exec "pip install" { & $VenvPython -m pip install -r "$Backend\requirements.txt" }
    }
    Done "backend dependencies installed"
    # Create/upgrade the app's tables in whatever DATABASE_URL (fastapi-seerver\.env) points at.
    Push-Location $Backend
    try { Exec "alembic upgrade head" { & "$Backend\.venv\Scripts\alembic.exe" upgrade head } } finally { Pop-Location }
    Done "database tables up to date (alembic)"

    Step "4. Frontend packages"
    # cd instead of --prefix: on Windows npm resolves --prefix to the parent folder
    Push-Location $Frontend
    try { Exec "npm install" { npm install --no-fund --no-audit } } finally { Pop-Location }
    Done "frontend dependencies installed"

    Step "5. Start FastAPI and the frontend in this terminal"
    if (Test-Port $ApiPort) { Skip "something already listens on :$ApiPort" }
    else {
        $started += Start-Process "$Backend\.venv\Scripts\fastapi.exe" -ArgumentList "dev", "app/main.py", "--port", "$ApiPort" `
            -WorkingDirectory $Backend -NoNewWindow -PassThru
        Done "FastAPI starting -> http://localhost:$ApiPort/docs"
    }
    if (Test-Port $WebPort) { Skip "something already listens on :$WebPort" }
    else {
        # node + vite.js instead of `npm run dev`: npm.cmd would ask "Terminate batch job (Y/N)?" on Ctrl+C
        $started += Start-Process node -ArgumentList "node_modules\vite\bin\vite.js" `
            -WorkingDirectory $Frontend -NoNewWindow -PassThru
        Done "Vite starting -> http://localhost:$WebPort"
    }
    $deadline = (Get-Date).AddSeconds(30)
    while (-not ((Test-Port $WebPort) -and (Test-Port $ApiPort)) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 1 }
    Start-Process "http://localhost:$WebPort"   # default browser

    Write-Host "`nAll set. The site opens as a guest: Sign in -> Log in (alice / alice123) or Sign in -> Register." -ForegroundColor Green

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
    # Also runs on Ctrl+C. /T kills child processes too (fastapi dev's reloader worker holds the API port).
    foreach ($p in $started) { taskkill /T /F /PID $p.Id *> $null }
}
