from pydantic import BaseModel

class DeviceResponse(BaseModel):
    id: int
    name: str
    model: str
    ip_address: str
    username: str
    password: str

class DeviceCreate(BaseModel):
    name: str
    model: str
    ip_address: str
    username: str
    password: str