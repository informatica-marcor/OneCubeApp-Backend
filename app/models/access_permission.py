from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer
from sqlalchemy.orm import relationship
from app.db.base import Base


class AccessPermission(Base):
    __tablename__ = "access_permissions"

    id = Column(Integer, primary_key=True, index=True)
    granted_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    grantee_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    valid_from = Column(DateTime(timezone=True), nullable=False)
    valid_to = Column(DateTime(timezone=True), nullable=False, index=True)

    granted_user = relationship("User", back_populates="granted_permissions", foreign_keys=[granted_user_id])
    grantee_user = relationship("User", back_populates="received_permissions", foreign_keys=[grantee_user_id])