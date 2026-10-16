from pydantic import BaseModel, EmailStr, Field
from app.core.config import settings
from app.schemas.user import UserBase

class LoginCodeRequest(BaseModel):
    email: EmailStr

class LoginCodeVerify(BaseModel):
    email: EmailStr
    code: str = Field(min_length=settings.code_length, max_length=settings.code_length)

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserBase