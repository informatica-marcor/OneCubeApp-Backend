from datetime import datetime
from typing import Optional
from pydantic import BaseModel

from app.schemas.warehouse import WarehouseBase

class LeaseOut(BaseModel):
    lease_id: int
    start_date: str
    end_date: str
    warehouse: WarehouseBase

    class Config:
        from_attributes = True


class LeaseCreate(BaseModel):
    client_id: int
    warehouse_id: int
    start_date: datetime
    end_date: datetime

    class Config:
        from_attributes = True