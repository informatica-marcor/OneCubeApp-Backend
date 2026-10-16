from __future__ import annotations
from datetime import timedelta
from sqlalchemy import or_, desc
from sqlalchemy.orm import Session, joinedload
from app.core.time import now_tz
from app.models import SupportTicket

class SupportTicketRepo:
    @staticmethod
    def create(db: Session, user_id: int, subject: str, description: str, status: str = "upload") -> SupportTicket:
        ticket = SupportTicket(
            user_id=user_id,
            subject=subject,
            description=description,
            status=status,
        )
        db.add(ticket)
        db.flush()
        return ticket

    @staticmethod
    def get_by_id(db: Session, ticket_id: int) -> SupportTicket | None:
        return db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()

    @staticmethod
    def get_all_by_user(db: Session, user_id: int) -> list[SupportTicket]:
        return (
            db.query(SupportTicket)
            .filter(SupportTicket.user_id == user_id)
            .order_by(desc(SupportTicket.created_at))
            .all()
        )

    @staticmethod
    def get_all(db: Session):
        five_days_ago = now_tz() - timedelta(days=5)

        return (
            db.query(SupportTicket)
            .options(joinedload(SupportTicket.user))
            .filter(
                or_(
                    SupportTicket.resolved_at.is_(None),
                    SupportTicket.resolved_at >= five_days_ago,
                )
            )
            .order_by(
                SupportTicket.resolved_at.isnot(None),
                desc(SupportTicket.created_at),
            )
            .all()
        )

    @staticmethod
    def delete(db: Session, ticket: SupportTicket) -> None:
        db.delete(ticket)