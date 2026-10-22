"""Pure tests for Vault cert fetching — no Docker/Vault; the httpx call is mocked."""
import os
import stat
from pathlib import Path

import httpx
import pytest

from app import secrets
from app.config import settings

BUNDLE = {"ca.crt": "CA-PEM", "client.crt": "CRT-PEM", "client.key": "KEY-PEM"}


@pytest.fixture
def vault(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "vault_token", "test-token")
    monkeypatch.setattr(settings, "db_cert_dir", str(tmp_path / "certs"))
    monkeypatch.setattr(settings, "vault_addr", "http://vault:8200")

    def respond(payload, status=200):
        monkeypatch.setattr(secrets.httpx, "get", lambda *a, **k: httpx.Response(status, json=payload))

    return respond


def test_writes_bundle_and_returns_ssl_kwargs(vault):
    vault({"data": {"data": BUNDLE}})
    ssl = secrets.ensure_db_certs()

    assert ssl["sslmode"] == "verify-full"
    assert Path(ssl["sslrootcert"]).read_text() == "CA-PEM"
    assert Path(ssl["sslcert"]).read_text() == "CRT-PEM"
    assert Path(ssl["sslkey"]).read_text() == "KEY-PEM"


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes not meaningful on Windows")
def test_key_written_0600(vault):
    vault({"data": {"data": BUNDLE}})
    ssl = secrets.ensure_db_certs()
    assert stat.S_IMODE(Path(ssl["sslkey"]).stat().st_mode) == 0o600


def test_missing_key_raises(vault):
    vault({"data": {"data": {"ca.crt": "CA-PEM"}}})  # client.crt/key absent
    with pytest.raises(RuntimeError, match="missing keys"):
        secrets.ensure_db_certs()


def test_non_200_raises(vault):
    vault({"errors": ["permission denied"]}, status=403)
    with pytest.raises(RuntimeError, match="403"):
        secrets.ensure_db_certs()


def test_no_token_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "vault_token", "")
    monkeypatch.setattr(settings, "vault_token_file", str(tmp_path / "nope"))
    with pytest.raises(RuntimeError, match="No Vault token"):
        secrets.ensure_db_certs()
