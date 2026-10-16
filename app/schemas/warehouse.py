from datetime import datetime
from typing import Optional
from pydantic import BaseModel

class WarehouseBase(BaseModel):
    id: int
    name: str
    location: str
    isolated: bool
    size_m2: int

    class Config:
        from_attributes = True


class WarehouseOut(BaseModel):
    id: int
    lease_id: Optional[int] = None
    name: str
    status: str
    location: str
    isolated: bool
    size_m2: int
    tenant: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None

    class Config:
        from_attributes = True