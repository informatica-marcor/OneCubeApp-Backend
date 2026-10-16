from datetime import datetime
from pydantic import BaseModel
from typing import Any


class DeviceEventIn(BaseModel):
    device_ip: str | None = None
    event_type: str
    event_time: datetime | None = None
    employee_no: str | None = None
    card_no: str | None = None
    door_no: str | None = None
    verify_mode: str | None = None
    raw_payload: dict[str, Any]

class DeviceEventOut(BaseModel):
    id: int
    device_id: int
    device_name: str | None
    user_name: str | None
    event_type: str
    employed_no: int | None
    created_at: str