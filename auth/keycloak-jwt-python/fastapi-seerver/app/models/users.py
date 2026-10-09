from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy import Identity, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


# --- table ---

class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True)
    email: Mapped[str] = mapped_column(String, unique=True)


# --- API schemas ---

class UserCreate(BaseModel):
    username: str
    email: EmailStr


class User(UserCreate):
    model_config = ConfigDict(from_attributes=True)  # User.model_validate(UserRow)

    id: int
