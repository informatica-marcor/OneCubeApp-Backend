from sqlalchemy.orm import Session
from app.core.security import encrypt_value, decrypt_value
from app.schemas.device import DeviceResponse
from app.models import Device

class DeviceRepo:
    @staticmethod
    def get_by_ip(db: Session, ip_address: str) -> Device:
        return db.query(Device).filter(Device.ip_address == ip_address).first()

    @staticmethod
    def get_all(db: Session) -> list[DeviceResponse]:
        devices = db.query(Device).all()

        return [
            DeviceResponse(
                id=device.id,
                name=device.name,
                model=device.model,
                ip_address=device.ip_address if device.ip_address else None,
                username=device.username if device.username else None,
                password=device.password if device.password else None,
            )
            for device in devices
        ]
    
    @staticmethod
    def create(db: Session, name: str, model: str, ip_address: str, username: str, password: str) -> Device:
        obj = Device(name=name, model=model, ip_address=ip_address, username=username, password=password)
        db.add(obj)
        db.flush()
        return obj