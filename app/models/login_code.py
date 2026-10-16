from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text, CheckConstraint, func
from sqlalchemy.orm import relationship
from app.db.base import Base


class LoginCode(Base):
    __tablename__ = "login_codes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    code_hash = Column(Text, nullable=False)

    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    attempts = Column(Integer, nullable=False, server_default="0")
    used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)

    user = relationship("User", back_populates="login_codes")

    __table_args__ = (
        CheckConstraint("attempts >= 0", name="chk_login_codes_attempts_nonnegative"),
        CheckConstraint("expires_at > created_at", name="chk_login_codes_expires_after_created"),
        CheckConstraint("used_at IS NULL OR used_at >= created_at", name="chk_login_codes_used_after_created"),
    )