# Data flow

> How a request moves through the system. Structure: [architecture.md](architecture.md) · entities: [datamodel.md](datamodel.md).

## 1. Public read (no key)

```
Browser/curl --GET /users/--> FastAPI --SELECT--> Postgres --rows--> 200
```

Reads declare no dependency, so they never touch `current_key`.

## 2. Write with a key

```
Browser/curl --POST /users/  X-API-Key: <key>--> FastAPI
   current_key:  sha256(<key>) ---SELECT api_keys WHERE key_hash=? AND active---> Postgres
      no row  -> 401 "Invalid or revoked API key"
      row     -> handler runs -> INSERT -> 201
```

Failure paths, all 401 before the handler runs:

| Situation | Where it fails |
|---|---|
| No `X-API-Key` header | `current_key` sees `None` → 401 "Missing API key" |
| Unknown key | hash not in `api_keys` → 401 |
| Revoked key | row exists but `active` is false, so the `WHERE` excludes it → 401 |

## 3. `/me`

```
GET /me  X-API-Key: <key>  ->  current_key returns the ApiKeyRow  ->  {"name", "prefix"}
```

Never returns `key_hash` or the raw key — the response model is `ApiKeyInfo` (name + prefix only).

## 4. Browser specifics

- The React app stores the key in `localStorage` (`auth/apiKey.ts`) and adds the `X-API-Key` header on every
  call when a key is set (`auth/apiFetch.ts`).
- CORS must allow the `X-API-Key` request header, or the browser blocks writes before they're sent
  (`main.py`, `allow_headers=["X-API-Key", "Content-Type"]`). curl isn't subject to CORS.
