from sqlalchemy import func

from app.core.time import now_tz
from sqlalchemy.orm import Session, joinedload
from app.models import Lease

class LeaseRepo:
    @staticmethod
    def get_by_id(db: Session, lease_id: int) -> Lease | None:
        return (
            db.query(Lease)
            .filter(Lease.id == lease_id)
            .first()
        )
    
    @staticmethod
    def create(
        db: Session,
        *,
        client_id: int,
        warehouse_id: int,
        start_date,
        end_date,
        created_by: int,
    ) -> Lease:
        lease = Lease(
            client_id=client_id,
            warehouse_id=warehouse_id,
            start_date=start_date,
            end_date=end_date,
            created_by=created_by,
        )
        db.add(lease)
        db.flush()
        return lease
    
    @staticmethod
    def get_active_lease_by_warehouse(db: Session, warehouse_id: int) -> Lease | None:
        now = now_tz()
        return (
            db.query(Lease)
            .filter(
                Lease.warehouse_id == warehouse_id,
                Lease.start_date <= now,
                Lease.end_date >= now,
                Lease.ended_date == None
            )
            .first()
        )

    @staticmethod
    def get_active_leases_by_client(db: Session, client_id: int) -> list[Lease]:
        return (
            db.query(Lease)
            .options(joinedload(Lease.warehouse)) 
            .filter(
                Lease.client_id == client_id,
                Lease.ended_date == None
            )
            .order_by(Lease.start_date.asc())
            .all()
        )
    
    def get_lease_date_range_by_client(db: Session, client_id: int):
        return (
            db.query(
                func.min(Lease.start_date).label("min_start"),
                func.max(Lease.end_date).label("max_end")
            )
            .filter(
                Lease.client_id == client_id,
                Lease.ended_date == None
            )
            .first()
        )
    
    @staticmethod
    def get_all_leases_by_client(db: Session, client_id: int) -> list[Lease]:
        return (
            db.query(Lease)
            .filter(Lease.client_id == client_id)
            .order_by(Lease.start_date.asc())
            .all()
        )