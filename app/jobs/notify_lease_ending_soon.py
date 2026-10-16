# app/jobs/notify_lease_ending_soon.py
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import selectinload

from app.core.time import now_tz
from app.db.session import SessionLocal
from app.models.lease import Lease
from app.services.email_service import send_lease_ending_soon_notification

DAYS_BEFORE_END_DATE_TO_NOTIFY = 15

def _should_notify_lease_ending_soon_today(
    lease: Lease,
    current_dt: datetime,
) -> bool:
    """
    Retorna True si el lease está activo y faltan exactamente 15 días
    para alcanzar su end_date.
    """
    today = current_dt.date()

    if lease.ended_date is not None:
        return False

    end_date = lease.end_date.date()

    if end_date <= today:
        return False

    notification_date = end_date - timedelta(days=DAYS_BEFORE_END_DATE_TO_NOTIFY)

    return today == notification_date


def notify_leases_ending_soon() -> dict[str, list[int]]:
    """
    Identifica leases activos a los que les faltan 15 días para terminar
    y envía un correo al cliente notificando que el contrato finalizará
    en end_date y que existe la posibilidad de extenderlo con un anexo.
    """
    db = SessionLocal()
    current_dt = now_tz()

    notified_lease_ids: list[int] = []
    failed_lease_ids: list[int] = []

    try:
        target_end_date = current_dt.date() + timedelta(
            days=DAYS_BEFORE_END_DATE_TO_NOTIFY
        )

        leases = (
            db.query(Lease)
            .options(selectinload(Lease.client))
            .filter(Lease.ended_date.is_(None))
            .filter(Lease.end_date >= target_end_date)
            .filter(Lease.end_date < target_end_date + timedelta(days=1))
            .all()
        )

        for lease in leases:
            if not _should_notify_lease_ending_soon_today(lease, current_dt):
                continue

            client = lease.client

            email_id: Optional[str] = send_lease_ending_soon_notification(
                to_email=client.email,
                user_name=client.name,
                lease_end_date=lease.end_date,
            )

            if email_id:
                notified_lease_ids.append(lease.id)

            else:
                failed_lease_ids.append(lease.id)

        db.commit()

        return {
            "notified_lease_ids": notified_lease_ids,
            "failed_lease_ids": failed_lease_ids,
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    result = notify_leases_ending_soon()
    print(result)