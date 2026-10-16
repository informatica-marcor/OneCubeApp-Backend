from __future__ import annotations

import secrets
import jwt

from cryptography.fernet import Fernet
from app.core.time import minutes_from_now
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordBearer
from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/verify-code")

fernet = Fernet(settings.encryption_key.encode())


def generate_login_code(length: int = settings.code_length) -> str:
    n = secrets.randbelow(10**length)
    return str(n).zfill(length)

def hash_code(code: str) -> str:
    return pwd_context.hash(code)

def verify_code(plain_code: str, code_hash: str) -> bool:
    return pwd_context.verify(plain_code, code_hash)

def create_access_token(data: dict, expires_minutes: int = settings.access_token_expire_minutes) -> str:
    to_encode = data.copy()
    expire = minutes_from_now(expires_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)

def encrypt_value(value: str) -> str:
    return fernet.encrypt(value.encode()).decode()

def decrypt_value(value: str) -> str:
    return fernet.decrypt(value.encode()).decode()