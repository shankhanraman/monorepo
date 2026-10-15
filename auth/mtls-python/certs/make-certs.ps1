<#
  Generate a self-signed CA, a server cert (nginx) and a client cert (curl / browser). Requires openssl.
  Run from anywhere:  powershell -ExecutionPolicy Bypass -File certs\make-certs.ps1
#>
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Some Windows installs set OPENSSL_CONF to a path that doesn't exist. Use our own minimal config.
Set-Content -Path openssl-min.cnf -Value "[req]`ndistinguished_name = dn`n[dn]" -Encoding ascii
$env:OPENSSL_CONF = "$PSScriptRoot\openssl-min.cnf"

Write-Host "==> CA"
openssl req -x509 -newkey rsa:2048 -nodes -keyout ca.key -out ca.crt -days 365 -subj "/CN=mtls-lab-CA" `
  -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign"

Write-Host "==> server cert (CN=localhost, SAN localhost + 127.0.0.1)"
Set-Content -Path san.cnf -Value "subjectAltName=DNS:localhost,IP:127.0.0.1" -Encoding ascii
openssl req -newkey rsa:2048 -nodes -keyout server.key -out server.csr -subj "/CN=localhost"
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out server.crt -days 365 -extfile san.cnf

Write-Host "==> client cert (CN=alice)"
openssl req -newkey rsa:2048 -nodes -keyout client.key -out client.csr -subj "/CN=alice"
openssl x509 -req -in client.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out client.crt -days 365

Write-Host "==> client.p12 for browser import (password: changeit)"
openssl pkcs12 -export -inkey client.key -in client.crt -certfile ca.crt -out client.p12 -passout pass:changeit

Remove-Item -Force server.csr, client.csr, ca.srl, san.cnf, openssl-min.cnf -ErrorAction SilentlyContinue
Write-Host "done: ca.crt, server.crt/key, client.crt/key, client.p12"
