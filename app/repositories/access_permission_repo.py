from datetime import datetime
from typing import Optional
from sqlalchemy import desc
from sqlalchemy.orm import Session
from app.models import AccessPermission, User
from app.core.time import now_tz

class AccessPermissionRepo:
    
    @staticmethod
    def get_by_id(db: Session, id: int) -> Optional[AccessPermission]:
        return db.query(AccessPermission).filter(AccessPermission.id == id).first()
    
    @staticmethod
    def get_all_by_granted_user_id(db: Session, granted_user_id: int):
        return (
            db.query(AccessPermission)
            .filter(AccessPermission.granted_user_id == granted_user_id)
            .order_by(AccessPermission.valid_from.desc())
            .all()
        )
    
    def get_active_access_permissions_by_user(db: Session, user_id: int) -> list[AccessPermission]:
        now = now_tz()

        return (
            db.query(AccessPermission)
            .join(User, User.id == AccessPermission.grantee_user_id)
            .filter(
                AccessPermission.granted_user_id == user_id,
                AccessPermission.valid_from <= now,
                AccessPermission.valid_to >= now,
                User.deleted_at.is_(None),
            )
            .all()
        )

    @staticmethod
    def get_latest_for_user(db: Session, user_id: int) -> Optional[AccessPermission]:
        return (
            db.query(AccessPermission)
            .filter(AccessPermission.grantee_user_id == user_id)
            .order_by(desc(AccessPermission.valid_from), desc(AccessPermission.id))
            .first()
        )
    
    @staticmethod
    def get_last_valid_access_permission(db: Session, grantee_user_id: int) -> Optional[AccessPermission]:
        return (
            db.query(AccessPermission)
            .filter(
                AccessPermission.grantee_user_id == grantee_user_id,
                AccessPermission.valid_to >= datetime.now(),
                AccessPermission.valid_from <= datetime.now(),
            ).first()
        )

    
    @staticmethod
    def create(
        db: Session,
        *,
        granted_user_id: int,
        grantee_user_id: int,
        valid_from: datetime,
        valid_to: datetime,
    ) -> AccessPermission:
        obj = AccessPermission(
            granted_user_id=granted_user_id,
            grantee_user_id=grantee_user_id,
            valid_from=valid_from,
            valid_to=valid_to,
        )
        db.add(obj)
        db.flush()
        return obj