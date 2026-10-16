from app.repositories.device_repo import DeviceRepo
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models import Device
import logging

def get_devices(db: Session, logger: logging.Logger) -> list[Device]:
    devices = DeviceRepo.get_all(db)
    if not devices:
        logger.warning("No biometric devices configured in the system")
        # raise HTTPException(
        #     status_code=status.HTTP_404_NOT_FOUND,
        #     detail="No biometric devices configured in the system",
        # )
    return devices