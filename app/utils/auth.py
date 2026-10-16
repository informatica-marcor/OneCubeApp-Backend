from typing import Annotated
from fastapi import Depends, HTTPException, status
from app.api.routers.auth import DBDep
from app.repositories.user_repo import UserRepo
from app.core.security import oauth2_scheme
from app.core.config import settings
import jwt

def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: DBDep,
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except Exception:
        raise credentials_exception

    user = UserRepo.get_by_id(db, int(user_id))
    if not user:
        raise credentials_exception

    return user