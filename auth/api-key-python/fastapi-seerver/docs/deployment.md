# Deployment notes

> **Status: lab only.** Today everything runs on one machine: Postgres in Docker (`:5438`), FastAPI via
> `fastapi dev` (`:8004`), Vite (`:5177`). See [architecture.md §4](architecture.md). This note lists what
> must change before an API-key service like this goes anywhere real.

## Before production

| Concern | Lab today | Production |
|---|---|---|
| Transport | plain HTTP | **HTTPS only** — an API key in a header is exposed on plain HTTP |
| Key issuance | seeded by migration `0002` | a **protected** `POST /keys` that generates a random key, stores its hash, and returns the plaintext **once** |
| Key lifecycle | `active` flag only | add **expiry**, rotation, and an audit of last-used time |
| Abuse | none | **rate-limit** by key; alert on bursts of 401s |
| Authorization | any valid key can write anything | scope keys to an owner and a permission set |
| Secrets | `.env`, keys documented in the repo | DB password in a secrets manager; keys never in source |
| Database | Postgres container | managed Postgres (e.g. AWS RDS) — change `DATABASE_URL` only |
| Build/test | by hand (`pytest`, `npm test`, `npm run build`) | CI on every PR |

## Generating a real key (shape to copy later)

```python
import secrets, hashlib
raw = "mial_live_" + secrets.token_urlsafe(32)   # show this to the caller exactly once
row = ApiKeyRow(name=name, prefix=raw[:12], key_hash=hashlib.sha256(raw.encode()).hexdigest(), active=True)
```

The verification side (`current_key`) stays unchanged — it only ever hashes-and-looks-up, so moving from
seeded keys to minted keys is additive.
