# Data flow

> How a request moves through the system. Structure: [architecture.md](architecture.md).

## 1. Public read (no client cert)

```
curl --cacert ca.crt GET /users/
  -> TLS handshake: nginx offers a cert request; client sends none (ssl_verify_client optional allows this)
  -> nginx sets X-SSL-Client-Verify: NONE  -> proxy to FastAPI -> reads are ungated -> 200
```

## 2. Write with a client cert

```
curl --cert client.crt --key client.key POST /users/
  -> TLS handshake: client presents client.crt
  -> nginx verifies it against ca.crt  -> X-SSL-Client-Verify: SUCCESS, X-SSL-Client-DN: CN=alice
  -> FastAPI current_cert sees SUCCESS -> handler runs -> 201
```

Failure paths (all 401 before the handler):

| Situation | nginx header | result |
|---|---|---|
| No client cert | `X-SSL-Client-Verify: NONE` | 401 |
| Cert not signed by our CA / expired | `X-SSL-Client-Verify: FAILED:<reason>` | 401 |
| (bypass attempt) forged header sent directly to FastAPI | — | connection refused: FastAPI isn't published |

## 3. `/me`

```
GET /me with a client cert -> current_cert returns {"cn": "alice"} (CN parsed from X-SSL-Client-DN)
GET /me without a cert     -> 401
```

## 4. Why the headers are trustworthy

`nginx.conf` uses `proxy_set_header X-SSL-Client-Verify $ssl_client_verify;` — `proxy_set_header` **replaces**
any value the client tried to send, so a caller can't inject their own. And the only way to reach FastAPI is
through nginx (the `server` container publishes no port), so a caller can't skip nginx either.
