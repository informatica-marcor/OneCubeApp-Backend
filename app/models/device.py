from sqlalchemy import Column, Integer, Text
from sqlalchemy.orm import relationship
from app.db.base import Base


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(Text, nullable=False)
    model = Column(Text, nullable=True)
    ip_address = Column(Text, nullable=True)
    username = Column(Text, nullable=True)
    password = Column(Text, nullable=True)

    events = relationship("DeviceEvent", back_populates="device")