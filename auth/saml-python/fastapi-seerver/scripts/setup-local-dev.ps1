<#
.SYNOPSIS
  One-command setup for the SAML lab on Windows. Needs Docker Desktop.

.DESCRIPTION
    1. .env from .env.example if missing
    2. docker compose up --build  ->  db + keycloak (SAML IdP :8083) + server (SAML SP :8006)

  Then drive SSO in a browser (http://localhost:8006/saml/login) or with ..\saml_login_test.py.
#>
$ErrorActionPreference = "Stop"
$Lab = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location $Lab

Write-Host "==> 1. .env" -ForegroundColor Cyan
if (-not (Test-Path .env)) { Copy-Item .env.example .env }

Write-Host "==> 2. docker compose up --build (first run compiles xmlsec, ~2-3 min)" -ForegroundColor Cyan
cmd /c "docker info >nul 2>&1"
if ($LASTEXITCODE -ne 0) { throw "Docker is not running. Start Docker Desktop and re-run." }
docker compose up --build -d

Write-Host "`nUp." -ForegroundColor Green
Write-Host "  Keycloak (IdP): http://localhost:8083  (admin / admin, realm saml-lab)"
Write-Host "  FastAPI  (SP) : http://localhost:8006   (/saml/login to start SSO)"
Write-Host "`nBrowser: open http://localhost:8006/saml/login -> sign in as alice / alice123." -ForegroundColor Green
Write-Host "Tests (in the container): docker compose run --rm server python -m pytest -q" -ForegroundColor Yellow
