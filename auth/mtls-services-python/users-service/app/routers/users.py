import itertools

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.dependencies import require_caller

router = APIRouter(prefix="/users", tags=["users"])

# ponytail: in-memory store, the lab is about transport identity (the other auth labs show Postgres)
_users: dict[int, dict] = {}
_ids = itertools.count(1)


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    email: str = Field(min_length=3, max_length=200)


@router.get("/")
def list_users(caller: str = require_caller("orders", "admin", "reporting")):
    return list(_users.values())


@router.get("/{user_id}")
def get_user(user_id: int, caller: str = require_caller("orders", "admin", "reporting")):
    if user_id not in _users:
        raise HTTPException(404, "User not found")
    return _users[user_id]


@router.post("/", status_code=201)
def create_user(data: UserCreate, caller: str = require_caller("admin")):
    user = {"id": next(_ids), **data.model_dump(), "created_by": caller}
    _users[user["id"]] = user
    return user
