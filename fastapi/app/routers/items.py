from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models.items import Item, ItemCreate
from app.services import items as service

router = APIRouter(prefix="/items", tags=["items"])


@router.post("/", response_model=Item, status_code=201)
def create_item(data: ItemCreate, db: Session = Depends(get_db)):
    return service.create_item(db, data)


@router.get("/", response_model=list[Item])
def list_items(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return service.list_items(db, limit, offset)


@router.get("/{item_id}", response_model=Item)
def get_item(item_id: int, db: Session = Depends(get_db)):
    item = service.get_item(db, item_id)
    if item is None:
        raise HTTPException(404, "Item not found")
    return item


@router.put("/{item_id}", response_model=Item)
def update_item(item_id: int, data: ItemCreate, db: Session = Depends(get_db)):
    item = service.update_item(db, item_id, data)
    if item is None:
        raise HTTPException(404, "Item not found")
    return item


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: int, db: Session = Depends(get_db)):
    if not service.delete_item(db, item_id):
        raise HTTPException(404, "Item not found")
