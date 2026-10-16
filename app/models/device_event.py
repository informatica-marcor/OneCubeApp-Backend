from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.core.time import now_tz

class DeviceEvent(Base):
    __tablename__ = "device_events"

    id = Column(Integer, primary_key=True, index=True)

    device_id = Column(Integer, ForeignKey("devices.id", ondelete="SET NULL"), nullable=False)
    name = Column(Text, nullable=True)
    employed_no = Column(Integer, nullable=True)
    event_type = Column(Text, nullable=False)
    raw_payload : Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now_tz())

    device = relationship("Device", back_populates="events")