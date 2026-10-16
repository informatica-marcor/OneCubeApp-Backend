from datetime import datetime
from pydantic import BaseModel

class EmailScheduleRunsBase(BaseModel):
    id: int
    schedule_id: int
    scheduled_for: datetime
    lease_id: int
    status: str
    sent_at: datetime | None
    failed_at: datetime | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

class EmailShedulesRunResponse(EmailScheduleRunsBase):
    pass

    class Config:
        from_attributes = True