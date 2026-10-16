from datetime import date, datetime
from pydantic import BaseModel

class EmailSchedulesBase(BaseModel):
    id: int
    subject: str
    body: str
    to: list[str]
    attachments: list[str] | None
    status: str
    trigger_type: str
    offset_days: int | None
    scheduled_for: date | None
    created_at: datetime
    updated_at: datetime

class EmailShedulesResponse(EmailSchedulesBase):
    pass

    class Config:
        from_attributes = True

class EmailScheduleDeletedResponse(EmailSchedulesBase):
    deleted_at: datetime

    class Config:
        from_attributes = True