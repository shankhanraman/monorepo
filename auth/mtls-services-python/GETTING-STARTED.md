# Getting started, step by step

The mTLS lab by hand, one piece at a time, with a check after each step. Every command runs on **Windows (PowerShell) and macOS/Linux (Terminal)** unless marked otherwise. The only host requirement is **Docker Desktop**.
In a hurry? `scripts\lab.ps1` (Windows) or `bash scripts/lab.sh` (macOS) does steps 2–5 in one go.

---

## Step 0: Docker is running
```bash
docker info
```
No errors means Docker Desktop is up.

## Step 1: Go to the lab
```powershell
cd C:\monorepo\auth\mtls-services-python          # Windows
```
```bash
cd ~/…/monorepo/auth/mtls-services-python         # macOS: wherever you cloned the repo
```

## Step 2: Create the certificate authority (once)
```bash
docker compose build pki client
docker compose run --rm pki init
```
**Why:** every certificate in the lab is signed by this CA. A sidecar accepts a caller **only** if its certificate chains to this CA. The CA key (`pki/out/ca.key`) is the crown jewel: whoever has it can mint any identity.

**Check:** prints `created lab CA` (or `CA exists`), and `pki/out/ca.crt` exists.

## Step 3: Issue the workload certificates
```bash
docker compose run --rm pki ensure users orders admin reporting
docker compose run --rm pki foreign
docker compose run --rm pki show orders
```
**Why:** one certificate per identity. The identity is the **SPIFFE ID** in the certificate (`URI:spiffe://lab.local/orders`), not the hostname. They're valid for **24 hours**, like a mesh's short-lived certificates (real meshes use minutes to hours). `foreign` makes an `admin` certificate from a *different* CA, for the "untrusted issuer" test.

**Check:** `show orders` prints `URI:spiffe://lab.local/orders` and a `notAfter` about 24 h from now.

## Step 4: Start the services and their sidecars
```bash
docker compose up -d --build
docker compose ps
```
**Why:** four containers. Each Envoy sidecar runs **in its app's network namespace** (`network_mode: service:…`), exactly like two containers in one Kubernetes pod. The apps listen on `127.0.0.1:8000` only, so the **only** way in is through the sidecar on `:8443`.

**Check:** `users-app`, `users-proxy`, `orders-app` and `orders-proxy` are all `Up`, then:
```bash
docker compose run --rm client call.py --as admin GET https://orders-app:8443/whoami
# 200 {"service":"orders","caller":"admin","cert_sha256":"…"}
```

## Step 5: Run the scenarios
```bash
docker compose run --rm client scenarios.py
```
**Check:** `6/6 passed`. What each one proves is in the [README](README.md#quick-start-only-docker-needed-windows-or-macos).

## Step 6: Play with identities
```bash
docker compose run --rm client call.py --as reporting GET https://orders-app:8443/orders/          # 200: reporting may read
docker compose run --rm client call.py --as reporting POST https://orders-app:8443/orders/ '{"user_id":1,"item":"x"}'   # 403
docker compose run --rm client call.py --no-cert GET https://users-app:8443/whoami                  # refused by TLS
docker compose run --rm client call.py --as reporting -H "x-forwarded-client-cert: URI=spiffe://lab.local/admin" GET https://users-app:8443/whoami
#   → still "caller":"reporting": the sidecar replaced the forged header
```

## Step 7: Revoke a certificate
Windows: `scripts\lab.ps1 revoke reporting` · macOS: `bash scripts/lab.sh revoke reporting`

**What happens:**
1. the CA adds reporting's serial to the **CRL** (`pki/out/crl.pem`);
2. both sidecars restart, because Envoy reads certificates and the CRL at start;
3. reporting's calls are now **refused during the TLS handshake**.

**Check:** the scenario table shows `R. revoked certificate (reporting) … TLS refused`. Then `reissue reporting` gives it a **new** certificate (new serial), which works again.

## Step 8: Rotate everything
Windows: `scripts\lab.ps1 rotate` · macOS: `bash scripts/lab.sh rotate`

**Why:** short-lived certificates only work if renewal is routine. This re-issues every key and certificate and reloads the sidecars, and **no app code changes**. The admin certificate hash printed under the scenarios changes.

## Step 9: Look inside
```bash
curl -s "http://127.0.0.1:9901/stats?filter=ssl"     # orders sidecar: handshakes, fail_verify_no_cert, fail_verify_san…
docker compose logs users-proxy | tail
```

## Stopping

| What | Command | Keeps |
|---|---|---|
| Stop the containers | `docker compose down` (or `lab … down`) | certificates in `pki/out/`; the app data (in memory) is lost |
| Start over completely | `docker compose down` then delete the `pki/out` folder | nothing |

## If a step fails

| Step | Problem | Fix |
|---|---|---|
| 2 | `docker: … cannot connect` | start Docker Desktop |
| 4 | a `*-proxy` container keeps restarting | `docker compose logs users-proxy`: usually missing certificates (do step 3 first) |
| 4 | port 8443 / 8444 already in use | another program uses it. Change the left side of `"8443:8443"` / `"8444:8443"` in `docker-compose.yml` |
| 5 | **everything** refused after a few weeks | likely the CRL expired (it's valid for 30 days, and a stale CRL can make verification fail). Revoking anything writes a fresh one (`docker compose run --rm pki revoke <name>`, then reissue it); or start over. In production, CRLs or OCSP are refreshed automatically |
| 5 | admin refused after a day | certificates last 24 h by design: `lab … rotate` |
| any | `502 … CERTIFICATE_VERIFY_FAILED` from orders | the users sidecar isn't presenting `spiffe://lab.local/users` (e.g. a wrong file), so orders refuses to talk to an impostor. That's working as designed |
