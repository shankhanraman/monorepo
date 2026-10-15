import itertools
import os

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.dependencies import require_caller

router = APIRouter(prefix="/orders", tags=["orders"])

# Plain HTTP to our own sidecar's egress port; the sidecar adds mTLS (our cert) and checks it's really "users".
USERS_URL = os.getenv("USERS_URL", "http://127.0.0.1:9001")

# ponytail: in-memory store, the lab is about transport identity
_orders: list[dict] = []
_ids = itertools.count(1)


class OrderCreate(BaseModel):
    user_id: int
    item: str = Field(min_length=1, max_length=100)


@router.get("/")
def list_orders(caller: str = require_caller("admin", "reporting")):
    return _orders


@router.post("/", status_code=201)
def create_order(data: OrderCreate, caller: str = require_caller("admin")):
    try:
        r = httpx.get(f"{USERS_URL}/users/{data.user_id}", timeout=5)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"users-service unreachable: {e}")
    if r.status_code == 404:
        raise HTTPException(404, "User not found")
    if r.status_code != 200:
        raise HTTPException(502, f"users-service answered {r.status_code}: {r.text[:200]}")
    order = {"id": next(_ids), **data.model_dump(), "user": r.json()["username"], "created_by": caller}
    _orders.append(order)
    return order
