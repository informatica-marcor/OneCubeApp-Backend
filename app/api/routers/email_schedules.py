from datetime import date
from pathlib import Path
import shutil
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.core.time import now_tz
from app.models.email_schedules import EmailSchedules
from app.models.email_schedule_runs import EmailScheduleRuns
from app.models.lease import Lease
from app.schemas.email_schedule_runs import EmailScheduleRunsBase
from app.schemas.email_schedules import EmailScheduleDeletedResponse, EmailShedulesResponse
from app.services.email_service import send_email
from app.utils.auth import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.core.config import settings
from app.utils.uploads import get_uploads_root

router = APIRouter(tags=["email_schedules"])
DBDep = Annotated[Session, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]

UPLOAD_ROOT = get_uploads_root() / "attachments"

VALID_TRIGGER_TYPES = {
    "immediate",
    "specific_date",
    "relative_to_lease_start",
    "relative_to_lease_end",
    "relative_to_payment_due",
    "recurring",
}

def validate_email_schedule_payload(
    *,
    to: list[str],
    subject: str,
    body: str,
    trigger_type: str,
    offset_days: Optional[int],
    scheduled_for: Optional[date],
):
    if not to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debes indicar al menos un destinatario.",
        )
    
    if not subject.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El asunto no puede estar vacío.",
        )

    if not body.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El cuerpo del correo no puede estar vacío.",
        )

    if trigger_type not in VALID_TRIGGER_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El tipo de disparador del correo no es válido.",
        )

    if trigger_type == "specific_date":
        if not scheduled_for:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debes indicar la fecha para el correo.",
            )

    if trigger_type == "recurring":
        if not scheduled_for:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debes indicar scheduled_for para correos recurrentes.",
            )

        if offset_days is None or offset_days <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debes indicar un Intervalo mayor a 0 para correos recurrentes.",
            )

    if trigger_type in {
        "relative_to_lease_start",
        "relative_to_lease_end",
        "relative_to_payment_due",
    }:
        if offset_days is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debes indicar offset_days para correos relativos a fechas del arriendo.",
            )

def save_email_attachments(
    *,
    email_schedule_id: int,
    attachments: Optional[list[UploadFile]],
) -> list[str]:
    """
    Guarda adjuntos en disco y retorna una lista de paths absolutos.
    Estos paths pueden guardarse en EmailSchedules.attachments.
    """

    if not attachments:
        return []

    email_dir = UPLOAD_ROOT / str(email_schedule_id)
    email_dir.mkdir(parents=True, exist_ok=True)

    saved_paths: list[str] = []

    for attachment in attachments:
        if not attachment or not attachment.filename:
            continue

        file_path = email_dir / attachment.filename

        with file_path.open("wb") as buffer:
            shutil.copyfileobj(attachment.file, buffer)

        saved_paths.append(str(file_path))

    return saved_paths

def validate_admin(current_user: CurrentUserDep):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para realizar esta acción.",
        )

# Rutas
@router.get("/email_schedules", response_model=list[EmailShedulesResponse], status_code=status.HTTP_200_OK)
def get_email_schedules(
    current_user: CurrentUserDep,
    db: DBDep,
):
    validate_admin(current_user)

    return (
        db.query(EmailSchedules)
        .filter(EmailSchedules.deleted_at.is_(None))
        .order_by(EmailSchedules.created_at.desc())
        .all()
    )

@router.get("/email_schedules_runs/{email_schedule_id}", response_model=list[EmailScheduleRunsBase], status_code=status.HTTP_200_OK)
def get_email_schedules_run(
    current_user: CurrentUserDep,
    db: DBDep,
    email_schedule_id: int,
):
    validate_admin(current_user)
    
    email_schedule = (
        db.query(EmailSchedules)
        .filter(
            EmailSchedules.id == email_schedule_id,
            EmailSchedules.deleted_at.is_(None)
        )
        .first()
    )
    
    if not email_schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontro el Email buscado.",
        )

    return (
        db.query(EmailScheduleRuns)
        .filter(
            EmailScheduleRuns.schedule_id == email_schedule_id
        )
        .all()
    )

@router.delete("/email_schedules/{email_schedule_id}", response_model=EmailScheduleDeletedResponse, status_code=status.HTTP_200_OK)
def delete_email_schedule(
    current_user: CurrentUserDep,
    db: DBDep,
    email_schedule_id: int,
):
    validate_admin(current_user)

    email_schedule = (
        db.query(EmailSchedules)
        .filter(
            EmailSchedules.id == email_schedule_id,
            EmailSchedules.deleted_at.is_(None),
            EmailSchedules.deleted_by.is_(None),
        )
        .first()
    )
    
    if not email_schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontro el elemento a eliminar.",
        )

    email_schedule.deleted_at = now_tz()
    email_schedule.deleted_by = current_user.id

    db.commit()
    db.refresh(email_schedule)

    return email_schedule

@router.post("/email_schedules/{email_schedule_id}/activate")
def activate_email_schedule(
    current_user: CurrentUserDep,
    db: DBDep,
    email_schedule_id: int,
):
    validate_admin(current_user)

    email_schedule = (
        db.query(EmailSchedules)
        .filter(
            EmailSchedules.id == email_schedule_id,
            EmailSchedules.deleted_at.is_(None),
            EmailSchedules.deleted_by.is_(None),
        )
        .first()
    )

    if not email_schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontro el elemento a activar.",
        )
    
    if email_schedule.status == "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No es posible activar un correo completado."
        )

    email_schedule.status = "active"
    db.commit()
    db.refresh(email_schedule)

    return email_schedule

@router.post("/email_schedules/{email_schedule_id}/deactivate")
def deactivate_email_schedule(
    current_user: CurrentUserDep,
    db: DBDep,
    email_schedule_id: int,
):
    validate_admin(current_user)

    email_schedule = (
        db.query(EmailSchedules)
        .filter(
            EmailSchedules.id == email_schedule_id,
            EmailSchedules.deleted_at.is_(None),
            EmailSchedules.deleted_by.is_(None),
        )
        .first()
    )

    if not email_schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontro el elemento a activar.",
        )
    
    if email_schedule.status == "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No es posible desactivar un correo completado."
        )

    email_schedule.status = "deactivated"
    db.commit()
    db.refresh(email_schedule)

    return email_schedule

@router.post("/email_schedules", response_model=EmailShedulesResponse, status_code=status.HTTP_201_CREATED)
def create_email_schedule(
    current_user: CurrentUserDep,
    db: DBDep,

    to: list[str] = Form(...),
    subject: str = Form(...),
    body: str = Form(...),
    attachments: list[UploadFile] | None = File(default=None),
    trigger_type: str = Form(...),
    offset_days: Optional[int] = Form(default=None),
    scheduled_for: Optional[date] = Form(default=None),
):
    validate_admin(current_user)

    validate_email_schedule_payload(
        to=to,
        subject=subject,
        body=body,
        trigger_type=trigger_type,
        offset_days=offset_days,
        scheduled_for=scheduled_for,
    )

    saved_attachment_paths: list[str] = []

    try:
        email_schedule = EmailSchedules(
            subject=subject,
            body=body,
            to=to,
            attachments=[],
            status="active",
            trigger_type=trigger_type,
            offset_days=offset_days,
            scheduled_for=scheduled_for,
            created_by=current_user.id,
        )

        db.add(email_schedule)
        db.flush()

        saved_attachment_paths = save_email_attachments(
            email_schedule_id=email_schedule.id,
            attachments=attachments or [],
        )

        email_schedule.attachments = saved_attachment_paths

        db.commit()
        db.refresh(email_schedule)

    except HTTPException:
        db.rollback()

        for path in saved_attachment_paths:
            Path(path).unlink(missing_ok=True)

        raise

    except Exception as e:
        db.rollback()

        for path in saved_attachment_paths:
            Path(path).unlink(missing_ok=True)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"No se pudo crear la programación de correo, Intentelo más tarde.",
        )
    
    if trigger_type != "immediate":
        return email_schedule

    current_datetime = now_tz()

    query = (
        db.query(Lease, User)
        .join(User, Lease.client_id == User.id)
        .filter(
            User.role == "client",
            User.deleted_at.is_(None),
            User.email.isnot(None),
            Lease.start_date <= current_datetime,
            Lease.end_date >= current_datetime,
        )
    )

    if email_schedule.to != ["*"]:
        query = query.filter(User.email.in_(email_schedule.to))

    lease_user_pairs = query.all()

    has_errors = False

    for lease, user in lease_user_pairs:
        run = EmailScheduleRuns(
            schedule_id=email_schedule.id,
            lease_id=lease.id,
            scheduled_for=current_datetime,
            status="pending",
        )

        db.add(run)
        db.flush()

        try:
            send_email(
                to=user.email,
                subject=subject,
                body=body,
                attachments=saved_attachment_paths,
            )

            run.status = "sent"
            run.sent_at = current_datetime

        except Exception as e:
            has_errors = True

            run.status = "failed"
            run.failed_at = current_datetime
            run.error_message = str(e)

        db.commit()

    if has_errors:
        email_schedule.status = "failed"
    else:
        email_schedule.status = "completed"

    db.commit()
    db.refresh(email_schedule)

    return email_schedule

@router.patch("/email_schedules/{email_schedule_id}", response_model=EmailShedulesResponse, status_code=status.HTTP_200_OK)
def update_email_schedule(
    email_schedule_id: int,
    current_user: CurrentUserDep,
    db: DBDep,

    to: Optional[list[str]] = Form(default=None),
    subject: Optional[str] = Form(default=None),
    body: Optional[str] = Form(default=None),

    existing_attachments: list[str] = Form(default=[]),
    attachments: Optional[list[UploadFile]] = File(default=None),

    trigger_type: Optional[str] = Form(default=None),
    offset_days: Optional[int] = Form(default=None),
    scheduled_for: Optional[date] = Form(default=None),

    schedule_status: Optional[str] = Form(default=None, alias="status"),
):
    validate_admin(current_user)

    email_schedule = (
        db.query(EmailSchedules)
        .filter(EmailSchedules.id == email_schedule_id)
        .first()
    )

    if not email_schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró la programación de correo.",
        )
    
    if trigger_type != email_schedule.trigger_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El tipo de correo nose puede modificar"
        )

    current_attachment_paths = list(email_schedule.attachments or [])
    saved_new_attachment_paths: list[str] = []
    removed_attachment_paths: list[str] = []

    try:
        final_to = to if to is not None else email_schedule.to
        final_subject = subject if subject is not None else email_schedule.subject
        final_body = body if body is not None else email_schedule.body

        final_offset_days = (
            offset_days if offset_days is not None else email_schedule.offset_days
        )

        final_scheduled_for = (
            scheduled_for if scheduled_for is not None else email_schedule.scheduled_for
        )

        validate_email_schedule_payload(
            to=final_to,
            subject=final_subject,
            body=final_body,
            trigger_type=email_schedule.trigger_type,
            offset_days=final_offset_days,
            scheduled_for=final_scheduled_for,
        )

        if schedule_status is not None:
            allowed_statuses = {"active", "deactivated", "completed", "failed"}

            if schedule_status not in allowed_statuses:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="El estado de la programación no es válido.",
                )

            email_schedule.status = schedule_status

        kept_attachment_paths = [
            path
            for path in existing_attachments
            if path in current_attachment_paths
        ]

        removed_attachment_paths = [
            path
            for path in current_attachment_paths
            if path not in kept_attachment_paths
        ]

        if attachments:
            saved_new_attachment_paths = save_email_attachments(
                email_schedule_id=email_schedule.id,
                attachments=attachments,
            )

        final_attachment_paths = kept_attachment_paths + saved_new_attachment_paths

        email_schedule.to = final_to
        email_schedule.subject = final_subject
        email_schedule.body = final_body
        #email_schedule.trigger_type = final_trigger_type
        email_schedule.offset_days = final_offset_days
        email_schedule.scheduled_for = final_scheduled_for
        email_schedule.attachments = final_attachment_paths

        db.commit()
        db.refresh(email_schedule)

    except HTTPException:
        db.rollback()

        for path in saved_new_attachment_paths:
            Path(path).unlink(missing_ok=True)

        raise

    except Exception as e:
        print(f"Ocurrió un error: {e}")
        db.rollback()

        for path in saved_new_attachment_paths:
            Path(path).unlink(missing_ok=True)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo actualizar la programación de correo. Inténtelo más tarde.",
        )

    for path in removed_attachment_paths:
        Path(path).unlink(missing_ok=True)

    return email_schedule

@router.get("/email_schedules/{email_schedule_id}/attachments/download")
def download_email_schedule_attachment(
    email_schedule_id: int,
    current_user: CurrentUserDep,
    db: DBDep,
    path: str = Query(...),
):
    validate_admin(current_user)

    email_schedule = (
        db.query(EmailSchedules)
        .filter(EmailSchedules.id == email_schedule_id)
        .first()
    )

    if not email_schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró la programación de correo.",
        )

    current_attachments = email_schedule.attachments or []

    if path not in current_attachments:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El archivo no pertenece a esta programación de correo.",
        )

    file_path = Path(path).resolve()

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró el archivo adjunto.",
        )

    return FileResponse(
        path=file_path,
        filename=file_path.name,
        media_type="application/octet-stream",
    )