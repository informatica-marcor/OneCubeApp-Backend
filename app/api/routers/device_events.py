import json
from typing import Annotated
import logging
from datetime import datetime

from fastapi import APIRouter, Request, Response, status, HTTPException, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.schemas.device_event import DeviceEventOut
from app.repositories.device_event_repo import DeviceEventRepo
from app.repositories.device_repo import DeviceRepo
from app.utils.auth import get_current_user

router = APIRouter(tags=["device_events"])
DBDep = Annotated[Session, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]

logger = logging.getLogger(__name__)

ACCESS_EVENT_TYPE_MAP: dict[tuple[int, int], str] = {
    (5, 75): "Acceso permitido",
    (5, 76): "Verificación fallida",
    (5, 8): "Permiso expirado",
}


def map_access_event_type(
    major_event_type: int | None,
    sub_event_type: int | None,
) -> str | None:
    if major_event_type is None or sub_event_type is None:
        return None

    return ACCESS_EVENT_TYPE_MAP.get((major_event_type, sub_event_type))

def format_device_datetime(raw_payload: dict) -> str | None:
    if not raw_payload:
        return None

    date_time = raw_payload.get("dateTime")

    if not date_time:
        return None

    try:
        parsed_date = datetime.fromisoformat(date_time)
        return parsed_date.strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return date_time

def build_event_detail(event) -> DeviceEventOut:
    raw_payload = event.raw_payload or {}
    access_event = raw_payload.get("AccessControllerEvent") or {}

    return DeviceEventOut(
        id=event.id,
        device_id=event.device_id,
        device_name=access_event.get("deviceName"),
        user_name=event.name,
        event_type=event.event_type,
        employed_no=event.employed_no,
        created_at=format_device_datetime(raw_payload),
    )

@router.get("/device-events", response_model=list[DeviceEventOut])
def get_device_events(current_user: CurrentUserDep, db: DBDep):
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    
    events = DeviceEventRepo.get_all(db)

    return [build_event_detail(event) for event in events]


@router.post("/device-events", status_code=status.HTTP_200_OK)
async def register_device_event(
    request: Request,
    db: DBDep,
):
    try:
        raw_body = await request.form()
        raw_event = raw_body.get("event_log")

        if not raw_event:
            return Response(status_code=status.HTTP_200_OK)

        try:
            event_data = json.loads(raw_event)
        except json.JSONDecodeError:
            return Response(status_code=status.HTTP_200_OK)

        access_event = event_data.get("AccessControllerEvent")
        if not isinstance(access_event, dict):
            return Response(status_code=status.HTTP_200_OK)

        ip_address = access_event.get("ipAddress") or event_data.get("ipAddress")
        if not ip_address:
            return Response(status_code=status.HTTP_200_OK)

        device = DeviceRepo.get_by_ip(db, ip_address)
        if not device:
            return Response(status_code=status.HTTP_200_OK)

        major_event_type = access_event.get("majorEventType")
        sub_event_type = access_event.get("subEventType")
        name = access_event.get("name")
        employed_no = access_event.get("employeeNoString")


        event_type = map_access_event_type(
            major_event_type=major_event_type,
            sub_event_type=sub_event_type,
        )

        if event_type is None:
            return Response(status_code=status.HTTP_200_OK)

        try:
            DeviceEventRepo.create(
                db=db,
                device_id=device.id,
                name=name,
                event_type=event_type,
                employed_no=employed_no,
                raw_payload=event_data,
            )
            db.commit()
        
        except Exception:
            db.rollback()

        return Response(status_code=status.HTTP_200_OK)

    except Exception:
        db.rollback()
        return Response(status_code=status.HTTP_200_OK)