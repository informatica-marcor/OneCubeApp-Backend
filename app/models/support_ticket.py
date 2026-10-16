from sqlalchemy import JSON, CheckConstraint, Column, DateTime, ForeignKey, Integer, Text
from app.core.time import now_tz
from sqlalchemy.orm import relationship
from app.db.base import Base


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    subject = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    status = Column(Text, nullable=False, server_default="upload")
    evidence = Column(JSON, nullable=True, default=list)

    reply_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reply = Column(Text, nullable=True)
    reply_evidence = Column(JSON, nullable=True, default=list)

    created_at = Column(DateTime(timezone=True), nullable=False, default=now_tz())
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="tickets",
    )

    reply_user = relationship(
        "User",
        foreign_keys=[reply_user_id],
        back_populates="replied_tickets",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('upload', 'resolved')",
            name="chk_support_tickets_status_valid",
        ),
    )