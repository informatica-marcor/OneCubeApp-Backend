from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship

from app.core.time import now_tz
from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    rut = Column(Text, nullable=True, index=True)
    name = Column(Text, nullable=True)
    phone = Column(Text, nullable=True)
    role = Column(Text, nullable=False)
    email = Column(Text, nullable=True, index=True)

    company_name = Column(Text, nullable=True)
    company_rut = Column(Text, nullable=True)

    photo = Column(Text, nullable=True)
    fingerprint = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=now_tz)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    updated_at = Column(DateTime(timezone=True), nullable=False, default=now_tz, onupdate=now_tz)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    deleted_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # -------------------------
    # Self-references
    # -------------------------

    updated_by_user = relationship(
        "User",
        foreign_keys=[updated_by],
        remote_side=[id],
        back_populates="updated_users",
    )

    updated_users = relationship(
        "User",
        foreign_keys=[updated_by],
        back_populates="updated_by_user",
    )

    deleted_by_user = relationship(
        "User",
        foreign_keys=[deleted_by],
        remote_side=[id],
        back_populates="deleted_users",
    )

    deleted_users = relationship(
        "User",
        foreign_keys=[deleted_by],
        back_populates="deleted_by_user",
    )

    # -------------------------
    # Related entities
    # -------------------------


    leases = relationship(
        "Lease",
        foreign_keys="Lease.client_id",
        back_populates="client",
        passive_deletes=True,
    )

    created_leases = relationship(
        "Lease",
        foreign_keys="Lease.created_by",
        back_populates="creator",
        passive_deletes=True,
    )

    granted_permissions = relationship(
        "AccessPermission",
        foreign_keys="AccessPermission.granted_user_id",
        back_populates="granted_user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    received_permissions = relationship(
        "AccessPermission",
        foreign_keys="AccessPermission.grantee_user_id",
        back_populates="grantee_user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    tickets = relationship(
        "SupportTicket",
        foreign_keys="SupportTicket.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    replied_tickets = relationship(
        "SupportTicket",
        foreign_keys="SupportTicket.reply_user_id",
        back_populates="reply_user",
        passive_deletes=True,
    )

    login_codes = relationship(
        "LoginCode",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint(
            "role IN ('system', 'admin', 'client', 'temporary')",
            name="chk_users_role_valid",
        ),
    )