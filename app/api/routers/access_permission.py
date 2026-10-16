from typing import Annotated
import logging
from app.core.config import settings

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.time import now_tz
from datetime import datetime
from app.db.session import get_db
from app.models.user import User
from app.repositories.access_permission_repo import AccessPermissionRepo
from app.repositories.user_repo import UserRepo
from app.schemas.access_permision import AccessPermissionIn
from app.utils.auth import get_current_user
from app.utils.devices import get_devices
from app.utils.hikvision import update_user_in_devices

router = APIRouter(tags=["access_permissions"])
DBDep = Annotated[Session, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]

logger = logging.getLogger(__name__)

@router.get("/access_permission/granted-by/{user_id}")
def get_access_permissions_granted_by_user(
    current_user: CurrentUserDep,
    user_id: int,
    db: DBDep,
):
    logger.info(
        "Get access permissions granted by user requested",
        extra={
            "actor_user_id": current_user.id,
            "actor_role": current_user.role,
            "target_user_id": user_id,
        },
    )

    user = UserRepo.get_by_id(db, user_id)
    if not user:
        logger.warning(
            "Get access permissions granted by user failed: user not found",
            extra={
                "actor_user_id": current_user.id,
                "target_user_id": user_id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if current_user.role != "admin" and current_user.id != user_id:
        logger.warning(
            "Get access permissions granted by user forbidden",
            extra={
                "actor_user_id": current_user.id,
                "target_user_id": user_id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )

    try:
        access_permissions = AccessPermissionRepo.get_all_by_granted_user_id(db, user_id)

        logger.info(
            "Get access permissions granted by user success",
            extra={
                "actor_user_id": current_user.id,
                "target_user_id": user_id,
                "count": len(access_permissions),
            },
        )

        return access_permissions

    except Exception:
        logger.exception(
            "Unexpected error while getting access permissions granted by user",
            extra={
                "actor_user_id": current_user.id,
                "target_user_id": user_id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error while getting access permissions granted by user",
        )

@router.post("/access_permission", status_code=status.HTTP_201_CREATED)
def create_access_permission(
    current_user: CurrentUserDep,
    payload: AccessPermissionIn,
    db: DBDep,
):
    logger.info(
        "Create access permission requested",
        extra={
            "actor_user_id": current_user.id,
            "actor_role": current_user.role,
            "grantee_user_id": payload.grantee_user_id,
            "valid_from": str(payload.valid_from),
            "valid_to": str(payload.valid_to),
        },
    )

    grantee_user = UserRepo.get_by_id(db, payload.grantee_user_id)
    if not grantee_user:
        logger.warning(
            "Create access permission failed: grantee user not found",
            extra={
                "actor_user_id": current_user.id,
                "grantee_user_id": payload.grantee_user_id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Grantee user not found",
        )
    
    if current_user.role != "admin" and grantee_user.created_by != current_user.id:
        logger.warning(
            "Create access permission forbidden",
            extra={
                "actor_user_id": current_user.id,
                "actor_role": current_user.role,
                "grantee_user_id": grantee_user.id,
                "grantee_created_by": grantee_user.created_by,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden"
        )
    
    if grantee_user.role != "temporary":
        logger.warning(
            "Create access permission failed: grantee is not temporary",
            extra={
                "actor_user_id": current_user.id,
                "grantee_user_id": grantee_user.id,
                "grantee_role": grantee_user.role,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Grantee user must be type temporary"
        )

    last_access_permission = AccessPermissionRepo.get_last_valid_access_permission(
        db,
        payload.grantee_user_id,
    )
    if last_access_permission is not None:
        logger.warning(
            "Create access permission failed: grantee already has an active permission",
            extra={
                "actor_user_id": current_user.id,
                "grantee_user_id": payload.grantee_user_id,
                "active_access_permission_id": getattr(last_access_permission, "id", None),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Grantee user already has an active access permission",
        )
    
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
    
    try:
        access_permission = AccessPermissionRepo.create(
            db=db,
            granted_user_id=current_user.id,
            grantee_user_id=payload.grantee_user_id,
            valid_from=payload.valid_from,
            valid_to=payload.valid_to,
        )

        logger.info(
            "Access permission created in session, syncing user in devices",
            extra={
                "actor_user_id": current_user.id,
                "grantee_user_id": payload.grantee_user_id,
                "access_permission_id": getattr(access_permission, "id", None),
            },
        )

        devices = get_devices(db=db, logger=logger)
        update_user_in_devices(
            user_id=payload.grantee_user_id,
            begin_time= payload.valid_from,
            end_time= payload.valid_to,
            devices=devices,
            logger=logger,
        )

        db.commit()
        db.refresh(access_permission)
        
        logger.info(
            "Access permission created successfully",
            extra={
                "actor_user_id": current_user.id,
                "grantee_user_id": payload.grantee_user_id,
                "access_permission_id": access_permission.id,
            },
        )
        return access_permission
    
    except HTTPException:
        logger.exception(
            "HTTPException while creating access permission",
            extra={
                "actor_user_id": current_user.id,
                "grantee_user_id": payload.grantee_user_id,
            },
        )
        db.rollback()
        raise
        
    except Exception:
        logger.exception(
            "Unexpected error while creating access permission",
            extra={
                "actor_user_id": current_user.id,
                "grantee_user_id": payload.grantee_user_id,
            },
        )
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error while creating access permission",
        )
    
@router.patch("/users/{access_permission_id}/end")
def end_access_permission(
    current_user: CurrentUserDep,
    access_permission_id: int,
    db: DBDep,
):
    actor_user_id = current_user.id
    actor_user_role = current_user.role

    logger.info(
        "End access permission requested",
        extra={
            "actor_user_id": actor_user_id,
            "actor_role": actor_user_role,
            "access_permission_id": access_permission_id,
        },
    )

    access_permission = AccessPermissionRepo.get_by_id(db, access_permission_id)
    if not access_permission:
        logger.warning(
            "End access permission failed: permission not found",
            extra={
                "actor_user_id": actor_user_id,
                "access_permission_id": access_permission_id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Access permission not found",
        )

    if actor_user_role != "admin" and access_permission.granted_user_id != actor_user_id:
        logger.warning(
            "End access permission forbidden",
            extra={
                "actor_user_id": actor_user_id,
                "access_permission_id": access_permission_id,
                "granted_user_id": access_permission.granted_user_id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )

    begin_time = access_permission.valid_from
    end_time = now_tz()

    if begin_time > end_time:
        begin_time = end_time

    try:
        access_permission.valid_to = end_time

        logger.info(
            "Access permission marked as ended in session, syncing devices",
            extra={
                "actor_user_id": actor_user_id,
                "access_permission_id": access_permission_id,
                "grantee_user_id": access_permission.grantee_user_id,
                "original_begin_time": str(access_permission.valid_from),
                "device_begin_time": str(access_permission.valid_from),
                "end_time": str(end_time),
                "was_adjusted_for_device": False,
            },
        )

        devices = get_devices(db=db, logger=logger)
        update_user_in_devices(
            user_id=access_permission.grantee_user_id,
            begin_time=begin_time,
            end_time=end_time,
            devices=devices,
            logger=logger,
        )

        db.commit()
        db.refresh(access_permission)

        logger.info(
            "Access permission ended successfully",
            extra={
                "actor_user_id": actor_user_id,
                "access_permission_id": access_permission_id,
                "grantee_user_id": access_permission.grantee_user_id,
                "end_time": str(end_time),
            },
        )

        return {
            "message": "Access permission ended successfully",
            "access_permission_id": access_permission.id,
            "ended_at": access_permission.valid_to,
        }

    except HTTPException:
        db.rollback()
        logger.exception(
            "HTTPException while ending access permission",
            extra={
                "actor_user_id": actor_user_id,
                "access_permission_id": access_permission_id,
            },
        )
        raise

    except Exception:
        db.rollback()
        logger.exception(
            "Unexpected error while ending access permission",
            extra={
                "actor_user_id": actor_user_id,
                "access_permission_id": access_permission_id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error while ending access permission",
        )