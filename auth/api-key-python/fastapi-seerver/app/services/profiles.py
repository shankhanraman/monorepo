from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.profiles import Profile, ProfileCreate, ProfileRow


def list_profiles(db: Session, user_id: int | None = None) -> list[Profile]:
    query = select(ProfileRow).order_by(ProfileRow.id)
    if user_id is not None:
        query = query.where(ProfileRow.user_id == user_id)
    return [Profile.model_validate(row) for row in db.scalars(query)]


def get_profile(db: Session, profile_id: int) -> Profile | None:
    row = db.get(ProfileRow, profile_id)
    return Profile.model_validate(row) if row else None


def create_profile(db: Session, data: ProfileCreate) -> Profile:
    row = ProfileRow(**data.model_dump())
    db.add(row)
    db.commit()
    return Profile.model_validate(row)


def update_profile(db: Session, profile_id: int, data: ProfileCreate) -> Profile | None:
    row = db.get(ProfileRow, profile_id)
    if row is None:
        return None
    row.user_id, row.bio = data.user_id, data.bio
    db.commit()
    return Profile.model_validate(row)


def delete_profile(db: Session, profile_id: int) -> bool:
    row = db.get(ProfileRow, profile_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True
