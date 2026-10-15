from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import require_login
from app.models.users import User, UserCreate
from app.services import users as service

router = APIRouter(prefix="/users", tags=["users"])


# --- public reads ---

@router.get("/", response_model=list[User])
def list_users(db: Session = Depends(get_db)):
    return service.list_users(db)


@router.get("/{user_id}", response_model=User)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = service.get_user(db, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return user


# --- writes: login required ---

@router.post("/", response_model=User, status_code=201, dependencies=require_login)
def create_user(data: UserCreate, db: Session = Depends(get_db)):
    return service.create_user(db, data)


@router.put("/{user_id}", response_model=User, dependencies=require_login)
def update_user(user_id: int, data: UserCreate, db: Session = Depends(get_db)):
    user = service.update_user(db, user_id, data)
    if not user:
        raise HTTPException(404, "User not found")
    return user


@router.delete("/{user_id}", status_code=204, dependencies=require_login)
def delete_user(user_id: int, db: Session = Depends(get_db)):
    """Also deletes the user's profiles."""
    if not service.delete_user(db, user_id):
        raise HTTPException(404, "User not found")
