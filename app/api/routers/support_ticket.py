from pathlib import Path
from typing import Annotated
from uuid import uuid4
import logging
import shutil

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.time import now_tz
from app.utils.auth import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.repositories.user_repo import UserRepo
from app.repositories.support_ticket_repo import SupportTicketRepo
from app.utils.uploads import get_uploads_root, public_upload_url
from app.schemas.tickets import TicketOut

router = APIRouter(tags=["support_ticket"])
DBDep = Annotated[Session, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]

logger = logging.getLogger(__name__)

UPLOAD_ROOT = get_uploads_root() / "tickets"


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)

def _build_ticket_dir(ticket_id: int, kind: str) -> Path:
    """
    kind:
    - created
    - resolved
    """
    return UPLOAD_ROOT / str(ticket_id) / kind

def _save_uploaded_images(
    *,
    images: list[UploadFile],
    upload_dir: Path,
    logger: logging.Logger,
    context: dict | None = None,
) -> list[str]:
    _ensure_dir(upload_dir)

    saved_paths: list[str] = []
    context = context or {}

    for image in images:
        if not image or not image.filename:
            logger.info(
                "Skipping empty uploaded file",
                extra=context,
            )
            continue

        extension = Path(image.filename).suffix.lower()
        unique_name = f"{uuid4().hex}{extension}"
        file_path = upload_dir / unique_name

        logger.info(
            "Saving uploaded image",
            extra={
                **context,
                "original_filename": image.filename,
                "target_path": str(file_path),
            },
        )

        try:
            image.file.seek(0)
            with file_path.open("wb") as buffer:
                shutil.copyfileobj(image.file, buffer)

            saved_paths.append(str(file_path))

        except Exception:
            logger.exception(
                "Failed to save uploaded image",
                extra={
                    **context,
                    "original_filename": image.filename,
                    "target_path": str(file_path),
                },
            )

            if file_path.exists():
                try:
                    file_path.unlink()
                except Exception:
                    logger.exception(
                        "Failed to delete partially saved file",
                        extra={
                            **context,
                            "target_path": str(file_path),
                        },
                    )
            raise

        finally:
            try:
                image.file.close()
            except Exception:
                logger.exception(
                    "Failed to close uploaded file stream",
                    extra={
                        **context,
                        "original_filename": image.filename if image else None,
                    },
                )

    return saved_paths

def build_ticket(ticket) -> TicketOut:
    return TicketOut(
        ticket_id=ticket.id,
        client_id=ticket.user_id,
        subject=ticket.subject,
        description=ticket.description,
        uploaded_at=ticket.created_at.strftime("%d/%m/%Y %H:%M"),
        reply_user_id=ticket.reply_user_id,
        # reply_user_name=ticket.reply_user_name,
        reply=ticket.reply,
        resolved_at=ticket.resolved_at.strftime("%d/%m/%Y %H:%M") if ticket.resolved_at else None
    )

def build_public_file_url(file_path: str) -> str | None:
    return public_upload_url(file_path)

def build_ticket_detail(ticket) -> dict:
    return {
        "ticket_id": ticket.id,
        "client_id": ticket.user_id,
        "client_name": ticket.user.name,
        "subject": ticket.subject,
        "description": ticket.description,
        "uploaded_at": ticket.created_at.strftime("%d/%m/%Y %H:%M"),
        "reply_user_id": ticket.reply_user_id,
        "reply": ticket.reply,
        "resolved_at": ticket.resolved_at.strftime("%d/%m/%Y %H:%M") if ticket.resolved_at else None,
        "images": [
            url
            for path in (ticket.evidence or [])
            if path and (url := build_public_file_url(path)) is not None
        ],
        "reply_images": [
            url
            for path in (ticket.reply_evidence or [])
            if path and (url := build_public_file_url(path)) is not None
        ],
    }

@router.get("/tickets/{ticket_id}")
def read_ticket(current_user: CurrentUserDep, ticket_id: int, db: DBDep):
    logger.info(
        "Read ticket requested",
        extra={
            "actor_user_id": current_user.id,
            "actor_role": current_user.role,
            "ticket_id": ticket_id,
        },
    )

    ticket = SupportTicketRepo.get_by_id(db, ticket_id)
    if not ticket:
        logger.warning(
            "Read ticket failed: ticket not found",
            extra={
                "actor_user_id": current_user.id,
                "ticket_id": ticket_id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        )

    if current_user.role != "admin" and current_user.id != ticket.user_id:
        logger.warning(
            "Read ticket forbidden",
            extra={
                "actor_user_id": current_user.id,
                "actor_role": current_user.role,
                "ticket_id": ticket_id,
                "ticket_owner_user_id": ticket.user_id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )

    logger.info(
        "Read ticket success",
        extra={
            "actor_user_id": current_user.id,
            "ticket_id": ticket_id,
        },
    )
    return build_ticket_detail(ticket)

@router.get("/tickets")
def read_tickets(current_user: CurrentUserDep, db: DBDep):
    logger.info(
        "Read all tickets requested",
        extra={
            "actor_user_id": current_user.id,
            "actor_role": current_user.role,
        },
    )

    if current_user.role != "admin":
        logger.warning(
            "Read all tickets forbidden",
            extra={
                "actor_user_id": current_user.id,
                "actor_role": current_user.role,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )

    tickets = SupportTicketRepo.get_all(db)

    logger.info(
        "Read all tickets success",
        extra={
            "actor_user_id": current_user.id,
            "count": len(tickets),
        },
    )

    return [build_ticket_detail(ticket) for ticket in tickets]

@router.get("/tickets/users/{user_id}", response_model=list[TicketOut])
def read_tickets_by_user(current_user: CurrentUserDep, user_id: int, db: DBDep):
    logger.info(
        "Read tickets by user requested",
        extra={
            "actor_user_id": current_user.id,
            "actor_role": current_user.role,
            "target_user_id": user_id,
        },
    )

    user_db = UserRepo.get_by_id(db, user_id)
    if not user_db:
        logger.warning(
            "Read tickets by user failed: user not found",
            extra={
                "actor_user_id": current_user.id,
                "target_user_id": user_id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if current_user.role != "admin" and current_user.id != user_id:
        logger.warning(
            "Read tickets by user forbidden",
            extra={
                "actor_user_id": current_user.id,
                "actor_role": current_user.role,
                "target_user_id": user_id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )

    tickets = SupportTicketRepo.get_all_by_user(db, user_id)

    logger.info(
        "Read tickets by user success",
        extra={
            "actor_user_id": current_user.id,
            "target_user_id": user_id,
            "count": len(tickets),
        },
    )
    return [build_ticket(ticket) for ticket in tickets]

@router.post("/ticket", status_code=status.HTTP_201_CREATED)
def create_ticket(
    current_user: CurrentUserDep,
    db: DBDep,
    subject: str = Form(...),
    description: str = Form(...),
    images: list[UploadFile] = File(default=[]),
):
    logger.info(
        "Create ticket requested",
        extra={
            "actor_user_id": current_user.id,
            "actor_role": current_user.role,
            "images_count": len(images),
            "subject_length": len(subject),
            "description_length": len(description),
        },
    )

    # Quitar admin
    if current_user.role != "admin" and current_user.role != "client":
        logger.warning(
            "Create ticket forbidden",
            extra={
                "actor_user_id": current_user.id,
                "actor_role": current_user.role,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )

    try:
        ticket = SupportTicketRepo.create(
            db,
            current_user.id,
            subject,
            description,
        )

        logger.info(
            "Ticket created in session",
            extra={
                "actor_user_id": current_user.id,
                "ticket_id": ticket.id,
            },
        )

        created_dir = _build_ticket_dir(ticket.id, "created")
        saved_paths = _save_uploaded_images(
            images=images,
            upload_dir=created_dir,
            logger=logger,
            context={
                "actor_user_id": current_user.id,
                "ticket_id": ticket.id,
                "upload_type": "created",
            },
        )

        ticket.evidence = saved_paths

        db.commit()
        db.refresh(ticket)

        logger.info(
            "Create ticket success",
            extra={
                "actor_user_id": current_user.id,
                "ticket_id": ticket.id,
                "saved_images_count": len(saved_paths),
            },
        )
        return ticket

    except HTTPException:
        logger.exception(
            "HTTPException while creating ticket",
            extra={
                "actor_user_id": current_user.id,
            },
        )
        db.rollback()
        raise

    except Exception:
        logger.exception(
            "Unexpected error while creating ticket",
            extra={
                "actor_user_id": current_user.id,
            },
        )
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error while creating ticket",
        )

@router.patch("/tickets/{ticket_id}/resolve")
def update_ticket(
    current_user: CurrentUserDep,
    db: DBDep,
    ticket_id: int,
    reply: str = Form(...),
    images: list[UploadFile] = File(default=[]),
):
    logger.info(
        "Resolve ticket requested",
        extra={
            "actor_user_id": current_user.id,
            "actor_role": current_user.role,
            "ticket_id": ticket_id,
            "images_count": len(images),
            "reply_length": len(reply),
        },
    )

    ticket = SupportTicketRepo.get_by_id(db, ticket_id)
    if ticket is None:
        logger.warning(
            "Resolve ticket failed: ticket not found",
            extra={
                "actor_user_id": current_user.id,
                "ticket_id": ticket_id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        )

    if current_user.role != "admin":
        logger.warning(
            "Resolve ticket forbidden",
            extra={
                "actor_user_id": current_user.id,
                "actor_role": current_user.role,
                "ticket_id": ticket_id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )

    try:
        resolved_dir = _build_ticket_dir(ticket.id, "resolved")
        saved_paths = _save_uploaded_images(
            images=images,
            upload_dir=resolved_dir,
            logger=logger,
            context={
                "actor_user_id": current_user.id,
                "ticket_id": ticket.id,
                "upload_type": "resolved",
            },
        )

        ticket.reply = reply
        ticket.reply_user_id = current_user.id
        ticket.status = "resolved"
        ticket.resolved_at = now_tz()
        ticket.reply_evidence = saved_paths

        db.commit()
        db.refresh(ticket)

        logger.info(
            "Resolve ticket success",
            extra={
                "actor_user_id": current_user.id,
                "ticket_id": ticket.id,
                "saved_images_count": len(saved_paths),
            },
        )
        return ticket

    except HTTPException:
        logger.exception(
            "HTTPException while resolving ticket",
            extra={
                "actor_user_id": current_user.id,
                "ticket_id": ticket_id,
            },
        )
        db.rollback()
        raise

    except Exception:
        logger.exception(
            "Unexpected error while resolving ticket",
            extra={
                "actor_user_id": current_user.id,
                "ticket_id": ticket_id,
            },
        )
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error while resolving ticket",
        )