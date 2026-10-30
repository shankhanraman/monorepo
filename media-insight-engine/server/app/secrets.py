"""Fetch the DB client certificate bundle from Vault at startup and write it to a tmpfs dir.

Swappable by design: the rest of the app only calls `ensure_db_certs()`. A Vault-PKI backend
(dynamic issuance) could replace the KV read here without touching db.py.

Vault stores the bundle in the KV v2 engine at `secret/<path>`; the HTTP read path has a `data/`
infix (`/v1/secret/data/<path>`) and the values live under `.data.data` in the response.
"""
import stat
from pathlib import Path

import httpx

from app.config import settings

# filename in Vault/tmpfs -> psycopg/libpq conninfo parameter
_CERT_FILES = {"ca.crt": "sslrootcert", "client.crt": "sslcert", "client.key": "sslkey"}

def _vault_token() -> str:
    if settings.vault_token:
        return settings.vault_token
    tok = Path(settings.vault_token_file)
    if tok.is_file():
        return tok.read_text(encoding="utf-8").strip()
    raise RuntimeError(
        f"No Vault token: set VAULT_TOKEN or provide VAULT_TOKEN_FILE ({settings.vault_token_file})"
    )

def _read_secret() -> dict[str, str]:
    url = f"{settings.vault_addr.rstrip('/')}/v1/secret/data/{settings.vault_db_cert_path}"
    try:
        resp = httpx.get(url, headers={"X-Vault-Token": _vault_token()}, timeout=10.0)
    except httpx.HTTPError as e:
        raise RuntimeError(f"Vault unreachable at {settings.vault_addr}: {e}") from e
    if resp.status_code != 200:
        raise RuntimeError(f"Vault read {url} failed: {resp.status_code} {resp.text[:200]}")
    data = (resp.json().get("data") or {}).get("data")
    if not data:
        raise RuntimeError(f"Vault secret '{settings.vault_db_cert_path}' has no data")
    missing = [k for k in _CERT_FILES if k not in data]
    if missing:
        raise RuntimeError(f"Vault secret '{settings.vault_db_cert_path}' missing keys: {missing}")
    return data

def ensure_db_certs() -> dict[str, str]:
    """Fetch the client bundle from Vault, write it 0600 into a tmpfs dir, return psycopg ssl kwargs."""
    data = _read_secret()
    cert_dir = Path(settings.db_cert_dir)
    cert_dir.mkdir(parents=True, exist_ok=True)
    cert_dir.chmod(stat.S_IRWXU)  # 0700
    ssl: dict[str, str] = {"sslmode": "verify-full"}
    for filename, param in _CERT_FILES.items():
        path = cert_dir / filename
        path.write_text(data[filename], encoding="utf-8")
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600 — libpq rejects a world-readable key
        ssl[param] = str(path)
    return ssl