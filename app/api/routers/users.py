import shutil
import logging

from pathlib import Path
from datetime import datetime
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, Form, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import EmailStr

from sqlalchemy.orm import joinedload
from collections import OrderedDict

from app.core.config import settings
from app.core.time import now_tz
from app.db.session import get_db
from app.utils.auth import get_current_user
from app.utils.devices import get_devices

from app.models.user import User
from app.models.access_permission import AccessPermission
from app.models.lease import Lease

from app.repositories.access_permission_repo import AccessPermissionRepo
from app.repositories.lease_repo import LeaseRepo
from app.repositories.user_repo import UserRepo
from app.schemas.user import (
    UserCreate,
    UserOut,
    VisitOut,
    UserUpdate,
    UserSummary,
    TemporaryUserPermissionOut,
    UserLeaseOut,
)
from app.services.email_service import (
    send_temporary_access_granted_email,
    send_portal_access_enabled_email
)
from app.utils.hikvision import (
    register_user_in_devices,
    update_user_in_devices,
    update_user_face_in_devices,
    register_user_face_in_devices,
    delete_user_in_devices
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["users"])

DBDep = Annotated[Session, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]

UPLOAD_ROOT = Path(settings.root) / "uploads" / "users"
DEFAULT_PROFILE_PHOTO = Path(settings.root) / "assets" / "default_profile_photo.jpg"

# --- UTILIDADES ---
def _normalize_email(email: Optional[str]) -> Optional[str]:
    if email is None:
        return None
    email = email.strip().lower()
    return email or None

def _save_user_photo(*, user_id: int, photo: UploadFile) -> str:
    if photo.content_type not in {"image/jpeg", "image/png"}:
        logger.warning(
            "Rejected photo upload for user_id=%s due to invalid content_type=%s",
            user_id,
            photo.content_type,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="photo must be image/jpeg or image/png",
        )

    user_dir = UPLOAD_ROOT / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)

    ext = ".jpg" if photo.content_type == "image/jpeg" else ".png"
    out_path = user_dir / f"photo{ext}"

    try:
        photo.file.seek(0)
        with out_path.open("wb") as f:
            shutil.copyfileobj(photo.file, f)
    except Exception as e:
        logger.exception("Failed to save photo for user_id=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save photo file"
        )

    logger.info("Photo saved for user_id=%s path=%s", user_id, out_path.as_posix())
    return str(out_path.as_posix())

def _cleanup_file(path: Optional[str]) -> None:
    if not path:
        return

    try:
        Path(path).unlink(missing_ok=True)
        logger.info("Cleaned up file path=%s", path)
    except Exception:
        logger.exception("Failed to cleanup file path=%s", path)

def _validate_exists_email(db: Session, email: Optional[str], *, exclude_user_id: Optional[int] = None) -> None:
    if not email:
        return

    existing_user = UserRepo.get_by_email(db, email)
    if existing_user and existing_user.id != exclude_user_id:
        logger.warning(
            "Conflicto de email detectado: el correo '%s' ya está en uso por el usuario ID: %s (ID excluido: %s)",
            email,
            existing_user.id,
            exclude_user_id,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El correo electrónico ya se encuentra registrado.",
        )

def build_visit_summary(visit) -> VisitOut:
    return VisitOut(
        id=visit.id,
        rut=visit.rut,
        name=visit.name,
        email=visit.email,
        lease_id=visit.access_permission_id,
        start_date=visit.valid_from.strftime("%d/%m/%Y %H:%M") if visit.valid_from else None,
        end_date=visit.valid_to.strftime("%d/%m/%Y %H:%M") if visit.valid_to else None,
    )

def build_public_file_url(file_path: str) -> str:
    uploads_root = (Path(settings.root) / "uploads").resolve()
    absolute_file_path = Path(file_path).resolve()

    relative_path = absolute_file_path.relative_to(uploads_root)
    version = int(absolute_file_path.stat().st_mtime)

    return f"{settings.public_base_url}/uploads/{relative_path.as_posix()}?v={version}"

def build_user_out(user) -> UserOut:
    user_image_url = None
    if user.photo and "default_profile_photo.jpg" not in user.photo:
        user_image_url = build_public_file_url(user.photo)

    return UserOut(
        user_id=user.id,
        rut=user.rut,
        name=user.name,
        image=user_image_url,
        email=user.email,
        role=user.role,
        company_name=user.company_name,
        company_rut=user.company_rut
    )

def build_temporary_user_out(user) -> TemporaryUserPermissionOut:
    user_image_url = None
    if user.grantee_user.photo and "default_profile_photo.jpg" not in user.grantee_user.photo:
        user_image_url = build_public_file_url(user.grantee_user.photo)

    return TemporaryUserPermissionOut(
        id=user.grantee_user.id,
        rut=user.grantee_user.rut,
        name=user.grantee_user.name,
        email=user.grantee_user.email,
        image=user_image_url,
        valid_from=user.valid_from.strftime("%d/%m/%Y %H:%M") if user.valid_from else None,
        valid_to=user.valid_to.strftime("%d/%m/%Y %H:%M") if user.valid_to else None
    ) 

# --- ENDPOINTS ---

@router.get("/me", response_model=UserOut)
def get_me(current_user: CurrentUserDep):
    logger.info("Current user requested own profile user_id=%s", current_user.id)
    return current_user

@router.get("/user/{user_id}/photo")
def get_photo_binary(user_id: int, current_user: CurrentUserDep, db: DBDep):
    logger.info(
        "Photo requested target_user_id=%s requester_user_id=%s requester_role=%s",
        user_id,
        current_user.id,
        current_user.role,
    )

    user_db = UserRepo.get_by_id(db, user_id)
    if not user_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if (
        current_user.role != "admin"
        and current_user.id != user_db.id
        and current_user.id != user_db.created_by
    ):
        logger.warning(
            "Photo request forbidden target_user_id=%s requester_user_id=%s",
            user_id,
            current_user.id,
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this photo")
    
    if not user_db.photo or not Path(user_db.photo).exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Physical photo file not found")

    photo_path = Path(user_db.photo)

    if photo_path.resolve() == DEFAULT_PROFILE_PHOTO.resolve():
        logger.info("Default photo detected for user_id=%s, returning 404 to trigger initials in UI", user_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="User has default photo, use initials"
        )

    if not photo_path.exists():
        logger.warning("Photo request failed: physical file not found target_user_id=%s", user_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Physical photo file not found")

    test = build_public_file_url(photo_path)
    return test

@router.get("/users/{user_id}", response_model=UserOut)
def read_user(user_id: int, current_user: CurrentUserDep, db: DBDep):
    user_db = UserRepo.get_by_id(db, user_id)
    if not user_db:
        logger.warning(
            "User read failed: user not found target_user_id=%s requester_user_id=%s",
            user_id,
            current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if current_user.role != "admin" and current_user.id != user_id:
        logger.warning(
            "User read forbidden target_user_id=%s requester_user_id=%s",
            user_id,
            current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized",
        )

    return build_user_out(user_db)

@router.get("/user/{user_id}/summary", response_model=UserSummary)
def read_user(user_id: int, current_user: CurrentUserDep, db: DBDep):
    user_db = UserRepo.get_by_id(db, user_id)
    if not user_db:
        logger.warning(
            "User read failed: user not found target_user_id=%s requester_user_id=%s",
            user_id,
            current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if current_user.role != "admin":
        logger.warning(
            "User read forbidden target_user_id=%s requester_user_id=%s",
            user_id,
            current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized",
        )

    permission_rows = (
        db.query(AccessPermission)
        .options(joinedload(AccessPermission.grantee_user))
        .filter(
            AccessPermission.granted_user_id == user_id,
            AccessPermission.grantee_user.has(User.deleted_at.is_(None)),
        )
        .order_by(
            AccessPermission.grantee_user_id.asc(),
            AccessPermission.valid_from.desc(),
            AccessPermission.id.desc(),
        )
        .all()
    )

    latest_permissions_by_grantee = OrderedDict()
    for permission in permission_rows:
        if permission.grantee_user_id not in latest_permissions_by_grantee:
            latest_permissions_by_grantee[permission.grantee_user_id] = permission


    # temporary_users = [
    #     TemporaryUserPermissionOut(
    #         id=permission.grantee_user.id,
    #         rut=permission.grantee_user.rut,
    #         name=permission.grantee_user.name,
    #         email=permission.grantee_user.email,
    #         photo=permission.grantee_user.photo,
    #         valid_from=permission.valid_from,
    #         valid_to=permission.valid_to,
    #     )
    #     for permission in latest_permissions_by_grantee.values()
    # ]

    lease_rows = (
        db.query(Lease)
        .options(joinedload(Lease.warehouse))
        .filter(
            Lease.client_id == user_id,
        )
        .order_by(Lease.start_date.desc(), Lease.id.desc())
        .all()
    )

    leases = [
        UserLeaseOut(
            id=lease.id,
            warehouse_id=lease.warehouse_id,
            warehouse_name=lease.warehouse.name,
            start_date=lease.start_date.strftime("%d/%m/%Y %H:%M") if lease.start_date else None,
            end_date=lease.end_date.strftime("%d/%m/%Y %H:%M") if lease.end_date else None,
            ended_date=lease.ended_date.strftime("%d/%m/%Y %H:%M") if lease.ended_date else None,
        )
        for lease in lease_rows
    ]

    logger.info(
        "User read successfully target_user_id=%s requester_user_id=%s",
        user_id,
        current_user.id,
    )

    return UserSummary(
        user=build_user_out(user_db),
        temporary_users=[build_temporary_user_out(user) for user in latest_permissions_by_grantee.values()],
        leases=leases,
    )

@router.get("/clients", response_model=list[UserOut])
def read_users(current_user: CurrentUserDep, db: DBDep):
    if current_user.role != "admin":
        logger.warning("Read users forbidden requester_user_id=%s role=%s", current_user.id, current_user.role)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tienes permiso para ver clientes.")

    logger.info("Admin requested users list requester_user_id=%s", current_user.id)
    clients = UserRepo.get_users_clients(db)

    return [build_user_out(client) for client in clients]

@router.get("/users/client/active")
def read_active_users(current_user: CurrentUserDep, db: DBDep):
    if current_user.role != "admin":
        logger.warning("Read active forbidden requester_user_id=%s role=%s", current_user.id, current_user.role)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tienes permiso para ver clientes.")

    logger.info("Admin requested active users list requester_user_id=%s", current_user.id)
    
    today = now_tz()

    return (
        db.query(User)
        .join(Lease, User.id == Lease.client_id)
        .filter(
            User.role == "client",
            Lease.start_date <= today,
            Lease.end_date >= today,
            User.deleted_at.is_(None),
        )
        .distinct()
        .all()
    )

@router.get("/users/{user_id}/visits")
def read_temporary_users(user_id: int, current_user: CurrentUserDep, db: DBDep):
    if current_user.role != "admin" and current_user.id != user_id:
        logger.warning(
            "Read temporary users forbidden target_user_id=%s requester_user_id=%s",
            user_id,
            current_user.id,
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    logger.info(
        "Temporary users requested for grantor_user_id=%s requester_user_id=%s",
        user_id,
        current_user.id,
    )
    visits = UserRepo.get_temporary_users_by_grantor_summary(db, user_id)
    range = LeaseRepo.get_lease_date_range_by_client(db, user_id)
    
    return {
        "visits": [build_visit_summary(visit) for visit in visits],
        "limit": range.max_end
    }

@router.post("/users/client", status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, current_user: CurrentUserDep, db: DBDep):
    if current_user.role not in {"system", "admin"}:
        logger.warning(
            "No tienes permisos para crear clientes requester_user_id=%s role=%s",
            current_user.id,
            current_user.role,
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tienes permisos para crear clientes.")

    normalized_email = _normalize_email(payload.email)
    devices = get_devices(db=db, logger=logger)
    _validate_exists_email(db, normalized_email)

    try:
        user_db = UserRepo.create(
            db=db,
            name=payload.name,
            rut=payload.rut,
            email=normalized_email,
            role="client",
            company_name=payload.company_name,
            company_rut=payload.company_rut,
            created_by=current_user.id,
        )
        user_db.updated_by = current_user.id
        user_db.photo = str(DEFAULT_PROFILE_PHOTO)
        db.flush()
        
        # register_user_in_devices(
        #     user_db=user_db,
        #     devices=devices,
        #     valid_from=now_tz(),
        #     valid_to=now_tz(),
        #     logger=logger,
        # )

        # register_user_face_in_devices(
        #     devices=devices,
        #     user_id=user_db.id,
        #     image_path=user_db.photo,
        #     logger=logger,
        # )

        db.commit()
        db.refresh(user_db)

        logger.info(
            "Client user created successfully user_id=%s created_by=%s",
            user_db.id,
            current_user.id,
        )

        return user_db

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        logger.exception("Client user creation failed requester_user_id=%s", current_user.id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

@router.post("/users/visit", status_code=status.HTTP_201_CREATED)
def create_temporary_user(
    name: str = Form(...),
    rut: str = Form(...),
    email: EmailStr = Form(...),
    start_date: datetime = Form(...),
    end_date: datetime = Form(...),
    photo: UploadFile | None = File(None),
    current_user: CurrentUserDep = None,
    db: DBDep = None,
):
    if current_user.role not in {"admin", "client"}:
        logger.warning(
            "Temporary user creation forbidden requester_user_id=%s role=%s",
            current_user.id,
            current_user.role,
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    normalized_email = _normalize_email(email)
    _validate_exists_email(db, normalized_email)

    access_permissions = AccessPermissionRepo.get_active_access_permissions_by_user(db, current_user.id)
    
    if len(access_permissions) >= settings.max_visits_per_user:
        logger.info(
            "Max temporary permissions reached for user_id=%s", 
            current_user.id
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Se ha alcanzado el máximo de 5 permisos simultáneos permitidos."
        )
        
    if start_date >= end_date:
        logger.warning(
            "Invalid temporary user date range requester_user_id=%s start=%s end=%s",
            current_user.id,
            start_date,
            end_date,
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="start_date must be earlier than end_date")
    print("pre devices")
    devices = get_devices(db=db, logger=logger)
    saved_photo_path = None

    try:
        
        user_db = UserRepo.create(
            db=db,
            name=name,
            email=normalized_email,
            rut=rut,
            role="temporary",
            created_by=current_user.id,
        )
        user_db.updated_by = current_user.id

        saved_photo_path = _save_user_photo(user_id=user_db.id, photo=photo)
        user_db.photo = saved_photo_path

        AccessPermissionRepo.create(
            db=db,
            granted_user_id=current_user.id,
            grantee_user_id=user_db.id,
            valid_from=start_date,
            valid_to=end_date,
        )

        # register_user_in_devices(
        #     user_db=user_db, 
        #     devices=devices,
        #     valid_from=start_date,
        #     valid_to=end_date,
        #     logger=logger,
        # )

        # register_user_face_in_devices(
        #     devices=devices,
        #     user_id=user_db.id,
        #     image_path=user_db.photo,
        #     logger=logger,
        # )

        db.commit()
        db.refresh(user_db)

        logger.info(
            "Temporary user created successfully user_id=%s granted_by=%s",
            user_db.id,
            current_user.id,
        )

        email_id = send_temporary_access_granted_email(
            to_email=user_db.email,
            user_name=user_db.name,
            start_date=start_date,
            end_date=end_date,
        )

        logger.info(
            "Temporary user notification processed user_id=%s email=%s email_sent=%s email_id=%s",
            user_db.id,
            user_db.email,
            bool(email_id),
            email_id,
        )

        return user_db

    except HTTPException:
        db.rollback()
        if saved_photo_path:
            try:
                Path(saved_photo_path).unlink(missing_ok=True)
            except Exception:
                logger.exception("Failed to remove saved profile photo path=%s", saved_photo_path)
        raise

    except Exception:
        db.rollback()
        if saved_photo_path:
            try:
                Path(saved_photo_path).unlink(missing_ok=True)
            except Exception:
                logger.exception("Failed to remove saved profile photo path=%s", saved_photo_path)

        logger.exception("Temporary user creation failed requester_user_id=%s", current_user.id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating temporary user")

@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdate, current_user: CurrentUserDep, db: DBDep):
    user_db = UserRepo.get_by_id(db, user_id)
    if not user_db:
        logger.warning("User update failed: user not found target_user_id=%s", user_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if current_user.role != "admin" and user_db.id != current_user.id:
        logger.warning(
            "User update forbidden target_user_id=%s requester_user_id=%s",
            user_id,
            current_user.id,
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    syncDevices = True

    try:
        if payload.name and user_db.name != payload.name:
            user_db.name = payload.name
            syncDevices = False
        
        if payload.rut and user_db.rut != payload.rut:
            user_db.rut = payload.rut
        
        if payload.email and user_db.email != payload.email:
            normalized_email = _normalize_email(payload.email)
            _validate_exists_email(db, normalized_email, exclude_user_id=user_db.id)
            user_db.email = normalized_email

        if payload.company_name and user_db.company_name != payload.company_name:
            user_db.company_name = payload.company_name
        
        if payload.company_rut and user_db.company_rut != payload.company_rut:
            user_db.company_rut = payload.company_rut

        user_db.updated_by = current_user.id
        db.flush()

        if not syncDevices:
            devices = get_devices(db=db, logger=logger)
            update_user_in_devices(
                user_id=user_id,
                name=user_db.name,
                devices=devices,
                logger=logger,
            )

        db.commit()
        db.refresh(user_db)

        logger.info(
            "User updated successfully target_user_id=%s updated_by=%s",
            user_db.id,
            current_user.id,
        )
        return user_db

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logger.exception(
            "User update failed target_user_id=%s requester_user_id=%s",
            user_id,
            current_user.id,
        )
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error during update")

@router.patch("/photo")
def update_face(
    user_id: str = Form(...),
    photo: UploadFile = File(...),
    current_user: CurrentUserDep = None,
    db: DBDep = None,
):
    user_id = int(user_id)

    if current_user.role != "admin" and current_user.id != user_id:
        logger.warning(
            "Face update forbidden target_user_id=%s requester_user_id=%s",
            user_id,
            current_user.id,
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    target_user = current_user if current_user.id == user_id else UserRepo.get_by_id(db, user_id)
    if not target_user:
        logger.warning("Face update failed: user not found target_user_id=%s", user_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    devices = get_devices(db=db, logger=logger)
    old_photo = target_user.photo
    saved_path = None

    try:
        saved_path = _save_user_photo(user_id=target_user.id, photo=photo)

    
        update_user_face_in_devices(
            user_db=target_user,
            devices=devices,
            image_path=saved_path,
            logger=logger,
        )

        target_user.photo = saved_path
        target_user.updated_by = current_user.id
        db.commit()

        if old_photo and old_photo != saved_path and old_photo != str(DEFAULT_PROFILE_PHOTO):
            _cleanup_file(old_photo)

        logger.info(
            "Face updated successfully target_user_id=%s updated_by=%s",
            target_user.id,
            current_user.id,
        )
        return {"message": "Face updated successfully"}

    except HTTPException:
        db.rollback()
        if saved_path:
            _cleanup_file(saved_path)
        raise
    except Exception:
        db.rollback()
        if saved_path:
            _cleanup_file(saved_path)
        logger.exception(
            "Face update failed target_user_id=%s requester_user_id=%s",
            user_id,
            current_user.id,
        )
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

@router.delete("/users/{user_id}")
def soft_delete_user(user_id: int, current_user: CurrentUserDep, db: DBDep):  
    user_db = UserRepo.get_by_id(db, user_id)
    if not user_db:
        logger.warning(
            "Soft delete failed: user not found target_user_id=%s requester_user_id=%s",
            user_id,
            current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    is_owner = current_user.id == user_db.created_by
    is_self = current_user.id == user_db.id

    if current_user.role != "admin" and not is_owner and not is_self:
        logger.warning(
            "Soft delete forbidden target_user_id=%s requester_user_id=%s requester_role=%s is_owner=%s is_self=%s",
            user_id,
            current_user.id,
            current_user.role,
            is_owner,
            is_self,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. This action is restricted to administrators, the creator of this record, or the user themself.",
        )

    try:
        logger.info(
            "Soft delete started target_user_id=%s requester_user_id=%s target_role=%s",
            user_db.id,
            current_user.id,
            user_db.role,
        )

        devices = get_devices(db=db, logger=logger)
        users_to_delete: list = []

        if user_db.role == "client":
            active_leases = LeaseRepo.get_active_leases_by_client(db, user_id)
            if active_leases:
                logger.warning(
                    "Soft delete blocked by active leases target_user_id=%s requester_user_id=%s",
                    user_id,
                    current_user.id,
                )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Lease activo, terminar contratos antes de eliminar usuario",
                )

            temporary_users = UserRepo.get_temporary_users_by_grantor(db, user_id) or []

            logger.info(
                "Temporary users linked to grantor found grantor_user_id=%s temporary_users_count=%s",
                user_id,
                len(temporary_users),
            )

            users_to_delete.extend(temporary_users)

        users_to_delete.append(user_db)

        for user in users_to_delete:
            UserRepo.soft_delete(
                db=db,
                user=user,
                deleted_by=current_user.id
            )

        db.flush()

        for user in users_to_delete:
            logger.info(
                "Deleting user in devices user_id=%s requester_user_id=%s",
                user.id,
                current_user.id,
            )

            delete_user_in_devices(
                user_id=user_id,
                devices=devices,
                logger=logger,
            )

            logger.info(
                "User deleted in devices successfully user_id=%s requester_user_id=%s",
                user.id,
                current_user.id,
            )

        db.commit()

        logger.info(
            "User soft deleted successfully target_user_id=%s requester_user_id=%s total_users_deleted=%s",
            user_id,
            current_user.id,
            len(users_to_delete),
        )

        return {
            "message": "User deleted successfully",
            "user_id": user_id,
        }

    except HTTPException:
        db.rollback()
        logger.warning(
            "Soft delete aborted by business rule target_user_id=%s requester_user_id=%s",
            user_id,
            current_user.id,
        )
        raise

    except Exception:
        db.rollback()
        logger.exception(
            "Soft delete failed target_user_id=%s requester_user_id=%s",
            user_id,
            current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error during delete",
        )