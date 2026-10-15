"""The app trusts only the sidecar's XFCC header; the call to users-service (via the egress sidecar) is mocked."""

from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def as_(name: str) -> dict:
    return {"x-forwarded-client-cert": f"By=spiffe://lab.local/orders;Hash=abc;URI=spiffe://lab.local/{name}"}


def users_answer(status: int, body: dict | None = None):
    return patch("app.routers.orders.httpx.get", return_value=httpx.Response(status, json=body or {}))


def test_create_order_checks_user_via_users_service():
    with users_answer(200, {"id": 1, "username": "carol"}) as call:
        r = client.post("/orders/", json={"user_id": 1, "item": "coffee"}, headers=as_("admin"))
    assert r.status_code == 201 and r.json()["user"] == "carol" and r.json()["created_by"] == "admin"
    assert call.call_args.args[0] == "http://127.0.0.1:9001/users/1"  # plain HTTP to our own sidecar, which adds mTLS

    with users_answer(404):
        assert client.post("/orders/", json={"user_id": 9, "item": "tea"}, headers=as_("admin")).status_code == 404
    with users_answer(403, {"detail": "nope"}):  # e.g. users-service refused our identity
        assert client.post("/orders/", json={"user_id": 1, "item": "tea"}, headers=as_("admin")).status_code == 502
    with patch("app.routers.orders.httpx.get", side_effect=httpx.ConnectError("refused")):
        assert client.post("/orders/", json={"user_id": 1, "item": "tea"}, headers=as_("admin")).status_code == 502


def test_authorization_by_caller():
    assert client.post("/orders/", json={"user_id": 1, "item": "x"}, headers=as_("reporting")).status_code == 403
    assert client.get("/orders/", headers=as_("reporting")).status_code == 200
    assert client.get("/orders/", headers=as_("users")).status_code == 403
    assert client.get("/orders/").status_code == 401
