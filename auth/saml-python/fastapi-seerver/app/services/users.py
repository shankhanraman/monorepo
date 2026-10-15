from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.users import User, UserCreate, UserRow


def list_users(db: Session) -> list[User]:
    return [User.model_validate(row) for row in db.scalars(select(UserRow).order_by(UserRow.id))]


def get_user(db: Session, user_id: int) -> User | None:
    row = db.get(UserRow, user_id)
    return User.model_validate(row) if row else None


def create_user(db: Session, data: UserCreate) -> User:
    """Raises sqlalchemy IntegrityError on a duplicate username/email (turned into 409 in main.py)."""
    row = UserRow(**data.model_dump())
    db.add(row)
    db.commit()
    return User.model_validate(row)


def update_user(db: Session, user_id: int, data: UserCreate) -> User | None:
    row = db.get(UserRow, user_id)
    if row is None:
        return None
    row.username, row.email = data.username, str(data.email)
    db.commit()
    return User.model_validate(row)


def delete_user(db: Session, user_id: int) -> bool:
    """The database deletes the user's profiles too (ON DELETE CASCADE)."""
    row = db.get(UserRow, user_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True
