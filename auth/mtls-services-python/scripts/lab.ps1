<#
.SYNOPSIS
  mTLS service-mesh lab: Windows (PowerShell). Only Docker is needed on the host.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\lab.ps1                    # setup + scenarios
  powershell -ExecutionPolicy Bypass -File scripts\lab.ps1 test               # run the scenarios again
  powershell -ExecutionPolicy Bypass -File scripts\lab.ps1 revoke reporting   # revoke, reload sidecars, show refusal
  powershell -ExecutionPolicy Bypass -File scripts\lab.ps1 reissue reporting  # fresh certificate
  powershell -ExecutionPolicy Bypass -File scripts\lab.ps1 rotate             # re-issue everything, zero app changes
  powershell -ExecutionPolicy Bypass -File scripts\lab.ps1 down
#>
param([string]$Command = "setup", [string]$Name)

Set-Location (Split-Path $PSScriptRoot -Parent)
$Identities = "users", "orders", "admin", "reporting"

function Run { docker compose run --rm -q @args; if ($LASTEXITCODE -ne 0) { $script:lastFailed = $true } }

function Wait-Ready {
    Write-Host -NoNewline "    waiting for both sidecars"
    for ($i = 0; $i -lt 30; $i++) {
        docker compose run --rm -q client call.py --as admin GET https://orders-app:8443/whoami *> $null
        $a = $LASTEXITCODE
        docker compose run --rm -q client call.py --as admin GET https://users-app:8443/whoami *> $null
        if ($a -eq 0 -and $LASTEXITCODE -eq 0) { Write-Host " ok"; return }
        Write-Host -NoNewline "."; Start-Sleep 2
    }
    throw "sidecars not ready: docker compose logs users-proxy orders-proxy"
}

function Reload-Sidecars { docker compose restart users-proxy orders-proxy | Out-Null; Wait-Ready }  # Envoy reads certs + CRL at start

switch ($Command) {
    "setup" {
        cmd /c "docker info >nul 2>&1"; if ($LASTEXITCODE -ne 0) { throw "Docker is not running. Start Docker Desktop, then re-run." }
        Write-Host "==> 1. Certificate authority and certificates (pki\out)" -ForegroundColor Cyan
        docker compose build -q pki client
        Run pki init
        Run pki ensure @Identities
        if (-not (Test-Path pki\out\foreign\admin.crt)) { Run pki foreign }
        Write-Host "==> 2. Start apps + sidecars" -ForegroundColor Cyan
        docker compose up -d --build
        Wait-Ready
        Write-Host "==> 3. Scenarios" -ForegroundColor Cyan
        Run client scenarios.py
    }
    "test"    { Run client scenarios.py }
    "revoke"  {
        if (-not $Name) { throw "usage: lab.ps1 revoke <name>" }
        Run pki revoke $Name; Reload-Sidecars
        Run client scenarios.py --revoked $Name
        Write-Host "`nTo let $Name in again with a NEW certificate: lab.ps1 reissue $Name"
    }
    "reissue" {
        if (-not $Name) { throw "usage: lab.ps1 reissue <name>" }
        Run pki issue $Name; Reload-Sidecars
        Run client call.py --as $Name GET https://users-app:8443/whoami
    }
    "rotate"  {
        Write-Host "==> Re-issuing every certificate (new keys, new serials)" -ForegroundColor Cyan
        foreach ($n in $Identities) { Run pki issue $n }
        Reload-Sidecars
        Run client scenarios.py
    }
    "down"    { docker compose down }
    default   { Get-Help $PSCommandPath -Examples; exit 2 }
}
