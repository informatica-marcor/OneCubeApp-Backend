from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey
from app.core.time import now_tz
from app.db.base import Base

class EmailScheduleRuns(Base):
    __tablename__ = "email_schedule_runs"

    id = Column(Integer, primary_key=True, index=True)
    schedule_id = Column(Integer, ForeignKey("email_schedules.id", ondelete="CASCADE"), nullable=False, index=True)
    lease_id = Column(Integer, ForeignKey("leases.id", ondelete="CASCADE"), nullable=False, index=True)
    scheduled_for = Column(DateTime(timezone=True), nullable=False, index=True)
    status = Column(Text, nullable=False, default="pending")
    sent_at = Column(DateTime(timezone=True), nullable=True)
    failed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now_tz)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=now_tz, onupdate=now_tz)