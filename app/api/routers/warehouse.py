import logging

from typing import Annotated, List, Optional
from datetime import datetime, MAXYEAR
from fastapi import Depends, APIRouter, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.warehouse_repo import WarehouseRepo
from app.models.warehouse import Warehouse
from app.schemas.warehouse import WarehouseOut
from app.utils.auth import get_current_user
from app.models.user import User


logger = logging.getLogger(__name__)
router = APIRouter(tags=["warehouse"])

DBDep = Annotated[Session, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


def build_warehouse_summary(warehouse: Warehouse) -> WarehouseOut:
    active_lease = next(
        (
            lease
            for lease in warehouse.leases
            if lease.ended_date is None
        ),
        None,
    )

    lease_id: Optional[int] = None
    tenant: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    status = "DISPONIBLE"

    if active_lease and active_lease.client:
        lease_id = active_lease.id
        tenant = active_lease.client.company_name or active_lease.client.name
        start_date = active_lease.start_date
        end_date = active_lease.end_date
        status = "OCUPADO"

    return WarehouseOut(
        id=warehouse.id,
        lease_id=lease_id,
        name=warehouse.name,
        status=status,
        isolated=warehouse.isolated,
        location=warehouse.location,
        tenant=tenant,
        size_m2=warehouse.size_m2,
        start_date=start_date.strftime("%d/%m/%Y %H:%M") if start_date else None,
        end_date=end_date.strftime("%d/%m/%Y %H:%M") if end_date else None,
    )


@router.get("/summary", response_model=List[WarehouseOut], status_code=status.HTTP_200_OK)
def get_warehouses_summary(current_user: CurrentUserDep, db: DBDep):
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    warehouses = WarehouseRepo.get_all(db)

    summaries_with_sort = []
    for warehouse in warehouses:
        active_lease = next(
            (
                lease
                for lease in warehouse.leases
                if lease.ended_date is None
            ),
            None,
        )

        summary = build_warehouse_summary(warehouse)

        is_available = summary.status == "DISPONIBLE"
        occupied_end_date = (
            active_lease.end_date if active_lease and active_lease.end_date else datetime(MAXYEAR, 12, 31)
        )

        summaries_with_sort.append(
            (summary, is_available, occupied_end_date, summary.id)
        )

    summaries_with_sort.sort(
        key=lambda item: (
            item[1],  # False (ocupado) primero, True (disponible) después
            item[2],  # entre ocupados: end_date más próximo
            item[3],  # entre disponibles: id
        )
    )

    return [item[0] for item in summaries_with_sort]