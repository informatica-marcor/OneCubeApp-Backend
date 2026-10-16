from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr

class AccessPermissionIn(BaseModel):
    grantee_user_id: int
    valid_from: datetime
    valid_to: datetime

    class Config:
        from_attributes = True

class AccessPermissionOut(BaseModel):
    id: int
    granted_user_id: int
    grantee_user_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)