from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_db
from app.models import Equipment

router = APIRouter(prefix="/api/equipment", tags=["equipment"])

DB = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[schemas.EquipmentOut])
def list_equipment(db: DB) -> list[Equipment]:
    return list(db.scalars(select(Equipment).order_by(Equipment.name)))


@router.patch("/{equipment_id}", response_model=schemas.EquipmentOut)
def update_equipment(equipment_id: int, body: schemas.EquipmentUpdate, db: DB) -> Equipment:
    equipment = db.get(Equipment, equipment_id)
    if equipment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Equipment not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(equipment, key, value)
    db.commit()
    return equipment
