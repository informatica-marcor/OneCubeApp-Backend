from sqlalchemy.orm import Session, joinedload
from app.models import Warehouse
from app.models import Lease


class WarehouseRepo:
    @staticmethod
    def get_all(db: Session) -> list[Warehouse]:
        return (
            db.query(Warehouse)
            .options(
                joinedload(Warehouse.leases).joinedload(Lease.client)
            )
            .order_by(Warehouse.id)
            .all()
        )

    @staticmethod
    def get_by_id(db: Session, warehouse_id: int) -> Warehouse | None:
        return db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()