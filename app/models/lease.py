from sqlalchemy import CheckConstraint, Column, DateTime, Date, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import relationship
from app.db.base import Base
from app.core.time import now_tz

class Lease(Base):
    __tablename__ = "leases"

    id = Column(Integer, primary_key=True, index=True)

    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=False, index=True)
    client_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False, index=True)

    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=False)

    created_at = Column(DateTime(timezone=True), nullable=False, default=now_tz())
    ended_date = Column(DateTime(timezone=True), nullable=True, default=None)

    client = relationship(
        "User",
        foreign_keys=[client_id],
        back_populates="leases",
        passive_deletes=True,
    )

    creator = relationship(
        "User",
        foreign_keys=[created_by],
        back_populates="created_leases",
        passive_deletes=True,
    )

    warehouse = relationship(
        "Warehouse",
        back_populates="leases",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint("end_date > start_date", name="chk_leases_end_after_start"),
        UniqueConstraint(
            "client_id",
            "warehouse_id",
            "start_date",
            "end_date",
            name="uq_leases_client_warehouse_period",
        ),
    )