from pydantic import BaseModel, ConfigDict
from sqlalchemy import ForeignKey, Identity, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


# --- table ---

class ProfileRow(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    # Deleting a user deletes their profiles, enforced by the database.
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    bio: Mapped[str] = mapped_column(String, default="", server_default="")


# --- API schemas ---

class ProfileCreate(BaseModel):
    user_id: int
    bio: str = ""


class Profile(ProfileCreate):
    model_config = ConfigDict(from_attributes=True)  # Profile.model_validate(ProfileRow)

    id: int
