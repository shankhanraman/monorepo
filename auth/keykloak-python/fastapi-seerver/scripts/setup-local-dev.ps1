<#
.SYNOPSIS
  One-command local setup for the Kerberos -> Keycloak -> FastAPI lab on Windows.

.DESCRIPTION
  Safe to re-run: every step checks first and skips what is already done.

  Machine steps (need admin; the script asks once through a Windows UAC prompt):
    1. MIT Kerberos for Windows (winget)    kinit/klist, plus gssapi64.dll that Firefox uses
    2. C:\ProgramData\MIT\Kerberos5\krb5.ini where the LAB.LOCAL KDC is (127.0.0.1, TCP)
    3. hosts entry for keycloak.lab.local    Kerberos tickets are tied to this hostname
    4. Firefox (winget) + autoconfig prefs   send Kerberos tickets to keycloak.lab.local via MIT

  User steps:
    5. .env files + docker compose up        Postgres + KDC + Keycloak + keycloak-init (needs Docker Desktop)
    6. backend .venv + requirements.txt      then `alembic upgrade head` (creates the app's tables)
    7. frontend npm install
    8. kinit <User>@LAB.LOCAL                asks for the password (alice: alice123)
    9. start FastAPI (:8000) and Vite (:5173) in this terminal, open Firefox; Ctrl+C stops both

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\setup-local-dev.ps1

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\setup-local-dev.ps1 -User bob
#>
param(
    [string]$User = "alice",
    [switch]$Elevated  # internal: set when the script re-launches itself as admin
)

$Backend  = Split-Path $PSScriptRoot -Parent
$Lab      = Split-Path $Backend -Parent
$Frontend = Join-Path $Lab "frontend"
$Compose  = Join-Path $Lab "docker-compose.yml"

$MitBin     = "C:\Program Files\MIT\Kerberos\bin"
$Krb5Ini    = "C:\ProgramData\MIT\Kerberos5\krb5.ini"
$HostsFile  = "$env:WINDIR\System32\drivers\etc\hosts"
$HostsLine  = "127.0.0.1 keycloak.lab.local kdc.lab.local"
$FirefoxDir = "C:\Program Files\Mozilla Firefox"

$Krb5IniText = @"
[libdefaults]
    default_realm = LAB.LOCAL
    dns_lookup_kdc = false
    dns_canonicalize_hostname = false
    rdns = false
    udp_preference_limit = 1

[realms]
    LAB.LOCAL = {
        kdc = 127.0.0.1
    }

[domain_realm]
    .lab.local = LAB.LOCAL
    keycloak.lab.local = LAB.LOCAL
"@

# Firefox autoconfig: autoconfig.js points at mozilla.cfg, whose first line must be a comment.
# defaultPref (not lockPref) so the values can still be changed in about:config.
$AutoconfigJs = @"
pref("general.config.filename", "mozilla.cfg");
pref("general.config.obscure_value", 0);
"@
$MozillaCfg = @"
// Kerberos lab prefs, written by fastapi-seerver/scripts/setup-local-dev.ps1
defaultPref("network.negotiate-auth.trusted-uris", "keycloak.lab.local");
defaultPref("network.auth.use-sspi", false);
defaultPref("network.negotiate-auth.gsslib", "C:\\Program Files\\MIT\\Kerberos\\bin\\gssapi64.dll");
"@

function Step($Message) { Write-Host "`n==> $Message" -ForegroundColor Cyan }
function Skip($Message) { Write-Host "    already done: $Message" -ForegroundColor DarkGray }
function Done($Message) { Write-Host "    $Message" -ForegroundColor Green }

# Run a native command and stop the script if it fails.
function Exec([string]$What, [scriptblock]$Command) {
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$What failed (exit code $LASTEXITCODE)" }
}

function Test-Admin {
    ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-FileText($Path, $Text) {
    (Test-Path $Path) -and ((Get-Content $Path -Raw) -eq $Text)
}

# krb5.ini and Firefox's cfg files break on a UTF-8 BOM, which PowerShell 5.1's Set-Content adds.
function Write-FileNoBom($Path, $Text) {
    New-Item -ItemType Directory -Force -Path (Split-Path $Path) -ErrorAction Stop | Out-Null
    [IO.File]::WriteAllText($Path, $Text)
}

function Test-HostsEntry {
    [bool](Select-String -Path $HostsFile -Pattern '^\s*127\.0\.0\.1\s.*\bkeycloak\.lab\.local\b' -Quiet)
}

function Test-MachineReady {
    (Test-Path "$MitBin\kinit.exe") -and
    (Test-FileText $Krb5Ini $Krb5IniText) -and
    (Test-HostsEntry) -and
    (Test-Path "$FirefoxDir\firefox.exe") -and
    (Test-FileText "$FirefoxDir\mozilla.cfg" $MozillaCfg)
}

function Install-WingetPackage([string]$Id, [string]$InstalledFile, [string[]]$Extra = @()) {
    if (Test-Path $InstalledFile) { Skip $Id; return }
    winget install --id $Id --exact --silent --accept-package-agreements --accept-source-agreements @Extra
    if (-not (Test-Path $InstalledFile)) { throw "winget install $Id finished but $InstalledFile is missing" }
    Done "installed $Id"
}

function Test-Port([int]$Port) {
    [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Invoke-MachineSetup {
    Step "1. MIT Kerberos for Windows"
    Install-WingetPackage "MIT.Kerberos" "$MitBin\kinit.exe"

    Step "2. Kerberos client config ($Krb5Ini)"
    if (Test-FileText $Krb5Ini $Krb5IniText) { Skip "krb5.ini" }
    else { Write-FileNoBom $Krb5Ini $Krb5IniText; Done "wrote krb5.ini (realm LAB.LOCAL, kdc 127.0.0.1)" }

    Step "3. hosts entry ($HostsLine)"
    if (Test-HostsEntry) { Skip "hosts entry" }
    else { Add-Content -Path $HostsFile -Value "`r`n$HostsLine" -Encoding ASCII -ErrorAction Stop; Done "added to $HostsFile" }

    Step "4. Firefox + Kerberos prefs"
    Install-WingetPackage "Mozilla.Firefox" "$FirefoxDir\firefox.exe" @("--scope", "machine")
    if (Test-FileText "$FirefoxDir\mozilla.cfg" $MozillaCfg) { Skip "Firefox prefs" }
    else {
        Write-FileNoBom "$FirefoxDir\defaults\pref\autoconfig.js" $AutoconfigJs
        Write-FileNoBom "$FirefoxDir\mozilla.cfg" $MozillaCfg
        Done "trusted-uris=keycloak.lab.local, use-sspi=false, gsslib=MIT gssapi64.dll"
    }
}

# Dot-sourcing (. .\setup-local-dev.ps1) only loads the functions, without running the setup.
if ($MyInvocation.InvocationName -eq '.') { return }

# --- Admin child process: machine steps only, then back to the normal window ---
if ($Elevated) {
    try { Invoke-MachineSetup; exit 0 }
    catch { Write-Host "`nFAILED: $_" -ForegroundColor Red; Read-Host "Press Enter to close"; exit 1 }
}

$started = @()  # server processes started by step 9, stopped again on exit
try {
    Step "Machine setup (MIT Kerberos, krb5.ini, hosts, Firefox)"
    if (Test-MachineReady) { Skip "all machine steps" }
    elseif (Test-Admin) { Invoke-MachineSetup }
    else {
        Write-Host "    needs admin rights: approve the Windows prompt (a second window shows progress)"
        $admin = Start-Process powershell -Verb RunAs -Wait -PassThru -ArgumentList @(
            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`"", "-Elevated")
        if ($admin.ExitCode -ne 0) { throw "machine setup failed in the admin window" }
        Done "machine setup finished"
    }

    Step "5. Docker: Postgres + KDC + Keycloak"
    # First run: create the .env files (passwords, database location) from the committed examples.
    foreach ($dir in $Lab, $Backend) {
        if (Test-Path "$dir\.env") { Skip "$dir\.env" }
        else { Copy-Item "$dir\.env.example" "$dir\.env" -ErrorAction Stop; Done "created $dir\.env from .env.example" }
    }
    cmd /c "docker info >nul 2>&1"
    if ($LASTEXITCODE -ne 0) { throw "Docker is not running. Start Docker Desktop, then re-run this script." }
    # Starts the `db` container only when .env has COMPOSE_PROFILES=local-db (otherwise: installed Postgres / AWS)
    Exec "docker compose up" { docker compose -f $Compose up -d --build }
    Write-Host "    waiting for keycloak-init (turns on the Kerberos login step)..."
    $deadline = (Get-Date).AddMinutes(3)
    do {
        Start-Sleep -Seconds 3
        $state = docker compose -f $Compose ps -a keycloak-init --format "{{.State}} {{.ExitCode}}"
    } until ($state -eq "exited 0" -or (Get-Date) -gt $deadline)
    if ($state -ne "exited 0") { throw "keycloak-init did not finish (state: $state). Check: docker compose logs keycloak-init" }
    Done "Keycloak ready at http://keycloak.lab.local:8080 (admin / admin)"

    Step "6. Backend Python environment ($Backend\.venv)"
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

    Step "7. Frontend packages"
    # cd instead of --prefix: on Windows npm resolves --prefix to the parent folder
    Push-Location $Frontend
    try { Exec "npm install" { npm install --no-fund --no-audit } } finally { Pop-Location }
    Done "frontend dependencies installed"

    Step "8. Kerberos ticket for $User@LAB.LOCAL"
    $tickets = & "$MitBin\klist.exe" 2>$null
    & "$MitBin\klist.exe" -s 2>$null
    if ($LASTEXITCODE -eq 0 -and ($tickets -match "Default principal: $User@LAB\.LOCAL")) { Skip "valid ticket for $User" }
    else {
        if ($User -eq "alice") { Write-Host "    password is alice123" }
        Exec "kinit" { & "$MitBin\kinit.exe" "$User@LAB.LOCAL" }
        Done "got TGT krbtgt/LAB.LOCAL@LAB.LOCAL"
    }

    Step "9. Start FastAPI and the frontend in this terminal"
    if (Test-Port 8000) { Skip "something already listens on :8000" }
    else {
        $started += Start-Process "$Backend\.venv\Scripts\fastapi.exe" -ArgumentList "dev", "app/main.py" `
            -WorkingDirectory $Backend -NoNewWindow -PassThru
        Done "FastAPI starting -> http://localhost:8000/docs"
    }
    if (Test-Port 5173) { Skip "something already listens on :5173" }
    else {
        # node + vite.js instead of `npm run dev`: npm.cmd would ask "Terminate batch job (Y/N)?" on Ctrl+C
        $started += Start-Process node -ArgumentList "node_modules\vite\bin\vite.js" `
            -WorkingDirectory $Frontend -NoNewWindow -PassThru
        Done "Vite starting -> http://localhost:5173"
    }
    $deadline = (Get-Date).AddSeconds(30)
    while (-not ((Test-Port 5173) -and (Test-Port 8000)) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 1 }
    Start-Process "$FirefoxDir\firefox.exe" "http://localhost:5173"

    Write-Host "`nAll set. The site opens as a guest: click Sign in -> Log in to get in as $User with no password prompt." -ForegroundColor Green
    Write-Host "If Firefox was already open before this run, close it fully and reopen so it loads the Kerberos prefs."
    Write-Host "Check the Kerberos service ticket: & `"$MitBin\klist.exe`"  (look for HTTP/keycloak.lab.local)"

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
    # Also runs on Ctrl+C. /T kills child processes too (fastapi dev's reloader worker holds port 8000).
    foreach ($p in $started) { taskkill /T /F /PID $p.Id *> $null }
}
