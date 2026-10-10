from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.items import Item, ItemCreate, ItemRow


def list_items(db: Session, limit: int, offset: int) -> list[Item]:
    rows = db.scalars(select(ItemRow).order_by(ItemRow.id).limit(limit).offset(offset))
    return [Item.model_validate(row) for row in rows]


def get_item(db: Session, item_id: int) -> Item | None:
    row = db.get(ItemRow, item_id)
    return Item.model_validate(row) if row else None


def create_item(db: Session, data: ItemCreate) -> Item:
    row = ItemRow(**data.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)  # load id and created_at, which the database fills in
    return Item.model_validate(row)


def update_item(db: Session, item_id: int, data: ItemCreate) -> Item | None:
    row = db.get(ItemRow, item_id)
    if row is None:
        return None
    for field, value in data.model_dump().items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return Item.model_validate(row)


def delete_item(db: Session, item_id: int) -> bool:
    row = db.get(ItemRow, item_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True
