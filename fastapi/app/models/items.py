from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, Identity, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.dependencies import Base


# --- table ---

class ItemRow(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(1000))
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))  # exact money, never float
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --- API schemas ---

class ItemCreate(BaseModel):
    """What a client sends (POST and PUT)."""

    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    price: Decimal = Field(ge=0, max_digits=10, decimal_places=2)


class Item(ItemCreate):
    """What the API returns."""

    model_config = ConfigDict(from_attributes=True)  # Item.model_validate(ItemRow)

    id: int
    created_at: datetime
