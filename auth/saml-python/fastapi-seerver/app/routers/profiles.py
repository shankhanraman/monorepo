from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import require_login
from app.models.profiles import Profile, ProfileCreate
from app.services import profiles as service
from app.services import users as user_service

router = APIRouter(prefix="/profiles", tags=["profiles"])


# --- public reads ---

@router.get("/", response_model=list[Profile])
def list_profiles(user_id: int | None = None, db: Session = Depends(get_db)):
    return service.list_profiles(db, user_id)


@router.get("/{profile_id}", response_model=Profile)
def get_profile(profile_id: int, db: Session = Depends(get_db)):
    profile = service.get_profile(db, profile_id)
    if not profile:
        raise HTTPException(404, "Profile not found")
    return profile


# --- writes: login required ---
# The "user exists" pre-checks give a clear 404; the foreign key still guards against races.

@router.post("/", response_model=Profile, status_code=201, dependencies=require_login)
def create_profile(data: ProfileCreate, db: Session = Depends(get_db)):
    if not user_service.get_user(db, data.user_id):
        raise HTTPException(404, "User not found")
    return service.create_profile(db, data)


@router.put("/{profile_id}", response_model=Profile, dependencies=require_login)
def update_profile(profile_id: int, data: ProfileCreate, db: Session = Depends(get_db)):
    if not user_service.get_user(db, data.user_id):
        raise HTTPException(404, "User not found")
    profile = service.update_profile(db, profile_id, data)
    if not profile:
        raise HTTPException(404, "Profile not found")
    return profile


@router.delete("/{profile_id}", status_code=204, dependencies=require_login)
def delete_profile(profile_id: int, db: Session = Depends(get_db)):
    if not service.delete_profile(db, profile_id):
        raise HTTPException(404, "Profile not found")
