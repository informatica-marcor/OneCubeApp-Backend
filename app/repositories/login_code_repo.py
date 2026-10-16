from __future__ import annotations
from datetime import datetime
from sqlalchemy import desc
from sqlalchemy.orm import Session
from app.models import LoginCode
from app.core.time import now_tz

class LoginCodeRepo:
    # Lo usa routers/auth.py
    @staticmethod
    def invalidate_active_codes(db: Session, user_id: int) -> None:
        active_codes =(
            db.query(LoginCode)
            .filter(
                LoginCode.user_id == user_id,
                LoginCode.used_at.is_(None),
                LoginCode.expires_at > now_tz(),
            )
            .all()
        )

        now = now_tz()
        for item in active_codes:
            item.used_at = now

        db.flush()


    # Lo usa routers/auth.py
    @staticmethod
    def create(db: Session, *, user_id: int, code_hash: str, expires_at: datetime) -> LoginCode:
        login_code = LoginCode(
            user_id=user_id,
            code_hash=code_hash,
            expires_at=expires_at,
        )
        db.add(login_code)
        db.flush()
        return login_code
    
    # Lo usa routers/auth.py
    @staticmethod
    def get_latest_valid_for_user(db: Session, user_id: int) -> LoginCode | None:
        return (
            db.query(LoginCode)
            .filter(
                LoginCode.user_id == user_id,
                LoginCode.used_at.is_(None),
                LoginCode.expires_at > now_tz(),
            )
            .order_by(desc(LoginCode.created_at), desc(LoginCode.id))
            .first()
        )
    
    # Lo usa routers/auth.py
    @staticmethod
    def increment_attempts(db: Session, login_code: LoginCode) -> None:
        login_code.attempts += 1
        db.flush()

    # Lo usa routers/auth.py
    @staticmethod
    def mark_as_used(db: Session, login_code: LoginCode) -> None:
        login_code.used_at = now_tz()
        db.flush()