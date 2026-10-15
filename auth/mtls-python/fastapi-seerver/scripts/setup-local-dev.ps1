<#
.SYNOPSIS
  One-command setup for the mTLS lab on Windows. Needs Docker Desktop + openssl.

.DESCRIPTION
    1. generate certs (CA + server + client) if missing
    2. .env from .env.example if missing
    3. docker compose up --build  ->  db + server (FastAPI, internal) + nginx (mTLS on :8443)

  FastAPI is not published; nginx :8443 is the only entry point.
#>
$ErrorActionPreference = "Stop"
$Lab = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location $Lab

Write-Host "==> 1. certificates" -ForegroundColor Cyan
if (Test-Path certs\ca.crt) { Write-Host "    already present (certs\ca.crt)" }
else { powershell -ExecutionPolicy Bypass -File certs\make-certs.ps1 }

Write-Host "==> 2. .env" -ForegroundColor Cyan
if (-not (Test-Path .env)) { Copy-Item .env.example .env }

Write-Host "==> 3. docker compose up --build" -ForegroundColor Cyan
cmd /c "docker info >nul 2>&1"
if ($LASTEXITCODE -ne 0) { throw "Docker is not running. Start Docker Desktop and re-run." }
docker compose up --build -d

Write-Host "`nUp. Windows curl uses Schannel, so add --ssl-no-revoke for the self-signed CA:" -ForegroundColor Green
Write-Host '  cd certs'
Write-Host '  curl --ssl-no-revoke --cacert ca.crt https://localhost:8443/users/        # 200 (public read)'
Write-Host "`nClient-cert writes from Windows curl need the cert in the Windows store, or use WSL / a Linux curl container (see README)." -ForegroundColor Yellow
