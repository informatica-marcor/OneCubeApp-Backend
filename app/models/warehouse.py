from sqlalchemy import Boolean, Column, DateTime, Integer, Text
from sqlalchemy.orm import relationship
from app.db.base import Base
from app.core.time import now_tz



class Warehouse(Base):
    __tablename__ = "warehouses"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(Text, nullable=False, unique=True)
    location = Column(Text, nullable=True)
    size_m2 = Column(Integer, nullable=True)
    isolated = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), nullable=False, default=now_tz())
    updated_at = Column(DateTime(timezone=True), nullable=False, default=now_tz(), onupdate=now_tz())

    leases = relationship(
        "Lease",
        back_populates="warehouse",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )