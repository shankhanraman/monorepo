# Deployment notes

> **Status: lab only.** Everything runs in Docker on one machine: nginx (`:8443`), FastAPI (internal), Postgres
> (`:5439`). See [architecture.md](architecture.md). This note lists what changes before real mTLS.

## Before production

| Concern | Lab today | Production |
|---|---|---|
| CA | self-signed, made by `make-certs` | a managed CA / internal PKI; rotate the CA and issued certs |
| Revocation | none | **CRL or OCSP** so a leaked client key can be revoked before expiry |
| Server cert | self-signed `CN=localhost` | a real cert for the real hostname (clients stop needing `--cacert`) |
| Authorization | any CA-signed cert can write | map CN/SAN → identity and roles; allowlist or per-client scopes |
| Trust boundary | `server` unpublished in compose | enforce with **network policy** (mesh / private subnet), optionally a shared secret proxy↔app |
| Where TLS ends | nginx container | an ingress / load balancer / service mesh doing the same `ssl_verify_client` + header forwarding |

## The pattern transfers unchanged

Kubernetes ingress-nginx exposes the same verification via annotations
(`nginx.ingress.kubernetes.io/auth-tls-verify-client: optional`) and forwards the same `ssl-client-verify` /
`ssl-client-subject-dn` info. A service mesh (Istio/Linkerd) does mTLS between pods and can pass the peer
identity similarly. In every case FastAPI's rule is the same: **trust the proxy's verdict, and make sure only
the proxy can reach you.** `app/dependencies.py` doesn't change.
