import logging
from datetime import datetime
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.repositories.warehouse_repo import WarehouseRepo
from app.services.email_service import send_portal_access_enabled_email
from app.utils.auth import get_current_user
from app.utils.devices import get_devices
from app.utils.hikvision import update_user_in_devices
from app.db.session import get_db
from app.core.time  import now_tz, ensure_tz, remove_tz
from app.models import Lease, User
from app.repositories.lease_repo import LeaseRepo
from app.repositories.user_repo import UserRepo
from app.schemas.lease import LeaseOut, LeaseCreate

router = APIRouter(tags=["leases"])
DBDep = Annotated[Session, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]

logger = logging.getLogger(__name__)

def get_effective_lease_range(
    leases: list[Lease],
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> tuple[datetime, datetime]:
    
    if not leases and (start_date is None or end_date is None):
        raise ValueError("Debes proporcionar leases o un rango de fechas válido")

    # Calcular desde leases si no vienen definidos
    leases_min_start = min((l.start_date for l in leases), default=start_date)
    leases_max_end = max((l.end_date for l in leases), default=end_date)

    # Determinar valores finales
    effective_start = min(
        [d for d in [start_date, leases_min_start] if d is not None]
    )

    effective_end = max(
        [d for d in [end_date, leases_max_end] if d is not None]
    )

    return effective_start, effective_end

def build_leases(lease) -> LeaseOut:
    return LeaseOut(
        lease_id=lease.id,
        client_id=lease.client_id,
        start_date=lease.start_date.strftime("%d/%m/%Y %H:%M") if lease.start_date else None,
        end_date=lease.end_date.strftime("%d/%m/%Y %H:%M") if lease.end_date else None,
        warehouse=lease.warehouse
    )


#ENDPOINTS
@router.get("/users/{user_id}/leases", response_model=list[LeaseOut])
def get_leases_by_client(current_user: CurrentUserDep, user_id: int, db: DBDep):
    if current_user.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    
    leases = LeaseRepo.get_active_leases_by_client(db, user_id)

    if not leases:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="USER_WITHOUT_ACTIVE_LEASE")
    
    return [build_leases(lease) for lease in leases]

@router.post("/leases")
def create_lease(current_user: CurrentUserDep, payload: LeaseCreate, db: DBDep):
    
    if current_user.role not in ["admin", "system"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para crear arriendos."
        )
    
    if payload.end_date <= payload.start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La fecha de término debe ser posterior a la fecha de inicio."    
        )

    client = UserRepo.get_by_id(db, payload.client_id)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró el cliente indicado."
        )
    
    if client.role != "client":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El usuario seleccionado no es un cliente."
        )
    
    warehouse = WarehouseRepo.get_by_id(db, payload.warehouse_id)
    if not warehouse:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró la bodega indicada."
        )
    
    is_occupied = LeaseRepo.get_active_lease_by_warehouse(db, payload.warehouse_id)
    if is_occupied is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La bodega seleccionada ya tiene un arriendo activo."
        )
    
    
    devices = get_devices(db=db, logger=logger)
    
    leases = LeaseRepo.get_lease_date_range_by_client(db, client.id)

    pay_start = ensure_tz(payload.start_date)
    pay_end = ensure_tz(payload.end_date)

    if leases and leases.min_start and leases.max_end:
        start_date = min(pay_start, leases.min_start)
        end_date = max(pay_end, leases.max_end)
    else:
        start_date = pay_start
        end_date = pay_end

    try:
        lease = LeaseRepo.create(
            db=db,
            client_id=payload.client_id,
            warehouse_id=payload.warehouse_id,
            start_date=payload.start_date,
            end_date=payload.end_date,
            created_by=current_user.id
        )
        
        # update_user_in_devices(
        #     user_id=client.id,
        #     begin_time=start_date,
        #     end_time=end_date,
        #     devices=devices,
        #     logger=logger,
        # )
        
        db.commit()
        db.refresh(lease)

    except HTTPException as e:
        db.rollback()
        raise
        
    except Exception as e:
        db.rollback()
        print(e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Unexpected error: {e}")
    
    send_portal_access_enabled_email(
        to_email=client.email,
        user_name=client.name,
    )
    
    return lease

@router.patch("/leases/{lease_id}/end")
def end_lease(current_user: CurrentUserDep, lease_id: int, db: DBDep):
    lease_db = LeaseRepo.get_by_id(db, lease_id)
    if not lease_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lease not found")
    
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    
    now = now_tz()
    devices = get_devices(db=db, logger=logger)

    try:
        lease_db.ended_date = now
        db.flush()

        remaining_leases = LeaseRepo.get_active_leases_by_client(
            db=db,
            client_id=lease_db.client_id
        )

        if remaining_leases:
            effective_start, effective_end = get_effective_lease_range(leases=remaining_leases)
            update_user_in_devices(
                user_id=lease_db.client_id,
                begin_time= effective_start,
                end_time= effective_end,
                devices=devices,
                logger=logger,
            )
                
        else:
            if lease_db.start_date < now:
                # El arriendo ya había comenzado
                update_user_in_devices(
                    user_id=lease_db.client_id,
                    begin_time=lease_db.start_date,
                    end_time=now,
                    devices=devices,
                    logger=logger,
                )
            else:
                # El arriendo todavía no comenzaba
                update_user_in_devices(
                    user_id=lease_db.client_id,
                    begin_time=now,
                    end_time=now,
                    devices=devices,
                    logger=logger,
                )

        db.commit()
        db.refresh(lease_db)

        return lease_db

    except HTTPException as e:
        db.rollback()
        raise
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Unexpected error: {e}")