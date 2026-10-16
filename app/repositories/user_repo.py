from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.access_permission import AccessPermission
from app.models import User
from app.core.time import now_tz

class UserRepo:

    def get_users_clients(db: Session):
        return (
            db.query(User)
            .filter(User.role == "client", User.deleted_at.is_(None))
            .all()
        )

    @staticmethod
    def get_temporary_users_by_grantor_summary(db: Session, user_id: int):
        latest_permission_subq = (
            db.query(
                AccessPermission.grantee_user_id.label("grantee_user_id"),
                func.max(AccessPermission.id).label("latest_access_permission_id"),
            )
            .filter(AccessPermission.granted_user_id == user_id)
            .group_by(AccessPermission.grantee_user_id)
            .subquery()
        )

        return (
            db.query(
                User.id,
                User.rut,
                User.name,
                User.email,
                User.photo,
                AccessPermission.id.label("access_permission_id"),
                AccessPermission.valid_from,
                AccessPermission.valid_to,
            )
            .join(
                latest_permission_subq,
                latest_permission_subq.c.grantee_user_id == User.id,
            )
            .join(
                AccessPermission,
                AccessPermission.id == latest_permission_subq.c.latest_access_permission_id,
            )
            .filter(
                User.role == "temporary",
                User.created_by == user_id,
                User.deleted_at.is_(None),
            )
            .order_by(AccessPermission.valid_to.desc())
            .all()
        )
    
    @staticmethod
    def get_temporary_users_by_grantor(db: Session, user_id: int):
        return (
            db.query(User)
            .filter(
                User.created_by == user_id,
                User.role == "temporary",
                User.deleted_at.is_(None)
            )
            .all()
        )
        
    @staticmethod
    def get_by_email(db: Session, email: str) -> Optional[User]:
        return db.query(User).filter(User.email == email, User.deleted_at.is_(None)).first()

    @staticmethod
    def get_by_id(db: Session, user_id: int) -> Optional[User]:
        return (
            db.query(User)
            .filter(
                User.id == user_id,
                User.deleted_at.is_(None)
            )
            .first()
        )

    @staticmethod
    def create(
        db: Session,
        *,
        name: str,
        rut: str,
        email: Optional[str] = None,
        role: str,
        company_name: Optional[str] = None,
        company_rut: Optional[str] = None,
        photo: Optional[str] = None,
        created_by: int
    ) -> User:
        obj = User(
            name=name,
            rut=rut,
            email=email,
            role=role,
            company_name=company_name,
            company_rut=company_rut,
            photo=photo,
            created_by=created_by
        )
        db.add(obj)
        db.flush()
        return obj
    
    @staticmethod
    def soft_delete(db: Session, user: User, deleted_by: int | None = None) -> User:
        user.deleted_at = now_tz()
        user.deleted_by = deleted_by
        db.flush()
        return user