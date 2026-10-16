from sqlalchemy.orm import Session
from app.models.device_event import DeviceEvent
from sqlalchemy import cast, DateTime, func, text

class DeviceEventRepo:
    @staticmethod
    def get_all(db: Session) -> list[DeviceEvent]:
        event_datetime = cast(
            DeviceEvent.raw_payload["dateTime"].astext,
            DateTime(timezone=True)
        )

        return (
            db.query(DeviceEvent)
            .filter(DeviceEvent.raw_payload["dateTime"].astext.isnot(None))
            .filter(event_datetime >= func.now() - text("interval '7 days'"))
            .order_by(event_datetime.desc())
            .all()
        )

class DeviceEventRepo:

    @staticmethod
    def get_all(db: Session) -> list[DeviceEvent]:
        event_datetime = cast(
            DeviceEvent.raw_payload["dateTime"].astext,
            DateTime(timezone=True)
        )

        return (
            db.query(DeviceEvent)
            .filter(DeviceEvent.raw_payload["dateTime"].astext.isnot(None))
            .filter(event_datetime >= func.now() - text("interval '7 days'"))
            .order_by(event_datetime.desc())
            .all()
        )

    @staticmethod
    def create(
        db: Session,
        *,
        device_id: int | None,
        name: str | None,
        employed_no: int | None,
        event_type: str,
        raw_payload: dict,
    ) -> DeviceEvent:
        event = DeviceEvent(
            device_id=device_id,
            name=name,
            event_type=event_type,
            employed_no=employed_no,
            raw_payload=raw_payload,
        )
        db.add(event)
        db.flush()
        return event