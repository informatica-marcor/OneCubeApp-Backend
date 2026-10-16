from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.models.user import User

from app.repositories.device_repo import DeviceRepo
from app.schemas.device import DeviceCreate
from app.utils.auth import get_current_user
from app.db.session import get_db
from app import models

router = APIRouter(tags=["devices"])
DBDep = Annotated[Session, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


@router.get("/device/{device_id}")
def read_device(device_id: int, db: DBDep):
    device = db.query(models.Device).filter(models.Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    return device

@router.get("/devices")
def read_devices(db: DBDep):
    return db.query(models.Device).all()

@router.post("/device", status_code=status.HTTP_201_CREATED)
def create_device(current_user: CurrentUserDep, payload: DeviceCreate, db: DBDep):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    
    try:
        device_db = DeviceRepo.create(
            db=db,
            name=payload.name,
            model=payload.model,
            ip_address=payload.ip_address,
            username=payload.username,
            password=payload.password
        )
        db.commit()
        db.refresh(device_db)
        return device_db
    
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")