from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr

class UserBase(BaseModel):
    id: int
    rut: str
    name: str
    email: EmailStr
    role: str
    company_name: Optional[str] = None
    company_rut: Optional[str] = None
    
    class Config:
        from_attributes = True

class UserOut(BaseModel):
    user_id: int
    image: Optional[str] = None
    rut: str
    name: str
    role: str
    email: str
    company_name: Optional[str] = None
    company_rut: Optional[str] = None

class VisitOut(BaseModel):
    id: int
    rut: str
    name: str
    email: str
    lease_id: int
    start_date: Optional[str] = None
    end_date: Optional[str] = None

class DetailsUserOut(BaseModel):
    id: int
    rut: str
    name: str
    role: str
    email: EmailStr
    company_name: Optional[str] = None
    company_rut: Optional[str] = None
    photo: Optional[str] = None
    fingerprint: Optional[str] = None
    created_at: datetime
    created_by: Optional[int]
    updated_at: Optional[datetime] = None
    updated_by: Optional[int] = None
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[int] = None

    class Config:
        from_attributes = True
    

class UserCreate(BaseModel):
    name: str
    rut: str
    email: EmailStr
    company_name: Optional[str] = None
    company_rut: Optional[str] = None

class UserUpdate(BaseModel):
    name: Optional[str] = None
    rut: Optional[str] = None
    email: Optional[EmailStr] = None
    company_name: Optional[str] = None
    company_rut: Optional[str] = None

# ----------------------------------------------
class TemporaryUserPermissionOut(BaseModel):
    id: int
    rut: Optional[str] = None
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    image: Optional[str] = None
    photo: Optional[str] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None

class UserLeaseOut(BaseModel):
    id: int
    warehouse_id: int
    warehouse_name: str
    start_date: str
    end_date: str
    ended_date: Optional[str] = None



class UserSummary(BaseModel):
    user: UserOut
    temporary_users: list[TemporaryUserPermissionOut]
    leases: list[UserLeaseOut]