from sqlalchemy import Column, Integer, Text, Date, DateTime, ForeignKey, ARRAY
from app.core.time import now_tz
from app.db.base import Base

class EmailSchedules(Base):
    __tablename__ = "email_schedules"

    id = Column(Integer, primary_key=True, index=True)

    subject = Column(Text, nullable=False)
    body = Column(Text, nullable=False)
    to = Column(ARRAY(Text), nullable=False)
    attachments = Column(ARRAY(Text), nullable=True)

    status = Column(Text, nullable=False, default="active")
    trigger_type = Column(Text, nullable=False)
    offset_days = Column(Integer, nullable=True)
    scheduled_for = Column(Date, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=now_tz())
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    updated_at = Column(DateTime(timezone=True), nullable=False, default=now_tz(), onupdate=now_tz())
    updated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)