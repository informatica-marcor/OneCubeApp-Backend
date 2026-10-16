from pathlib import Path
from typing import Annotated

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, generate_login_code, hash_code, verify_code
from app.core.time import minutes_from_now
from app.db.session import get_db
from app.repositories.lease_repo import LeaseRepo
from app.repositories.login_code_repo import LoginCodeRepo
from app.repositories.user_repo import UserRepo
from app.schemas.auth import LoginCodeRequest, LoginCodeVerify, TokenResponse
from app.services.email_service import send_login_code_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])
DBDep = Annotated[Session, Depends(get_db)]

########## Rutas ##############

@router.post("/request-code", status_code=status.HTTP_200_OK)
def request_login_code(payload: LoginCodeRequest, db: DBDep):
    try:
        user = UserRepo.get_by_email(db, payload.email)
        if not user:
            logger.warning("Login code request rejected: user not found for email=%s", payload.email)
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
        if user.role not in ["admin", "client"]:
            logger.warning("Login code request rejected: user_id=%s email=%s role=%s not authorized", user.id, user.email, user.role)   
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not authorized")

        is_active = LeaseRepo.get_active_leases_by_client(db, user.id)
        if (user.role == "client" and not is_active):
            logging.warning("Login code request rejected: no active leases for user_id=%s email=%s", user.id, user.email)
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not autorized")

        

        active_code = LoginCodeRepo.get_latest_valid_for_user(db, user.id)
        if active_code:
            logger.info("Login code request rejected: active code already exists for user_id=%s email=%s", user.id, user.email)
            return {"message": "Active login code already exists"}

        code = generate_login_code()
        print("code", code)
        code_hash = hash_code(code)
        expires_at = minutes_from_now(settings.code_ttl_minutes)

        LoginCodeRepo.create(db, user_id=user.id, code_hash=code_hash, expires_at=expires_at)
        db.commit()
        logger.info("Login code created successfully for user_id=%s email=%s expires_at=%s", user.id, user.email, expires_at)

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        logger.exception("Unexpected error while requesting login code for email=%s", payload.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error occurred while sending login code",
        )
    
    try:
        send_login_code_email(to_email=user.email, code=code, expires_minutes=settings.code_ttl_minutes)
        logger.info("Login code email sent successfully to user_id=%s email=%s", user.id, user.email)
    
    except Exception:
        logger.exception("Login code was created but email delivery failed for user_id=%s email=%s", user.id, user.email)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Login code generated, but the email could not be sent")

    return {"message": "Login code sent successfully"}


@router.post("/verify-code", response_model=TokenResponse, status_code=status.HTTP_200_OK)
def verify_login_code(payload: LoginCodeVerify, db: DBDep):
    try:
        user = UserRepo.get_by_email(db, payload.email)
        if not user:
            logger.warning("Login code verification failed: user not found for email=%s", payload.email)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User not found",
            )
    
        login_code = LoginCodeRepo.get_latest_valid_for_user(db, user.id)
        if not login_code:
            logger.warning(
                "Login code verification failed: no active code for user_id=%s email=%s",
                user.id,
                user.email,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired code",
            )

        if login_code.attempts >= settings.max_attempts:
            logger.warning(
                "Login code verification blocked: max attempts exceeded for user_id=%s email=%s attempts=%s",
                user.id,
                user.email,
                login_code.attempts,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Maximum attempts exceeded",
            )
        
        if not verify_code(payload.code, login_code.code_hash):
            LoginCodeRepo.increment_attempts(db, login_code)
            db.commit()

            logger.warning(
                "Login code verification failed: invalid code for user_id=%s email=%s attempts=%s",
                user.id,
                user.email,
                login_code.attempts + 1,
            )

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired code",
            )
        
        LoginCodeRepo.mark_as_used(db, login_code)    
        access_token = create_access_token({"sub": str(user.id)})
        db.commit()

        logger.info("Login code verified successfully for user_id=%s email=%s", user.id, user.email)
    
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            user=user,
        )
    
    except HTTPException:
        db.rollback()
        raise
    
    except Exception:
        db.rollback()
        logger.exception("Unexpected error during code verification for email=%s", payload.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error during code verification",
        )