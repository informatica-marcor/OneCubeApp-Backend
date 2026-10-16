# app/jobs/notify_payment_due.py

from __future__ import annotations

import calendar
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import selectinload

from app.core.time import now_tz
from app.db.session import SessionLocal
from app.models.lease import Lease
from app.services.email_service import send_payment_due_notification


def _get_last_day_of_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _get_payment_due_day_for_month(
    *,
    lease_start_day: int,
    year: int,
    month: int,
) -> int:
    """
    Retorna el día de cobro correspondiente para el mes actual.

    Ejemplos:
    - Si el arriendo empezó un día 15, cobra todos los días 15.
    - Si empezó un día 31 y el mes actual tiene 30 días, cobra el día 30.
    - Si empezó un día 30 o 31 y el mes actual es febrero, cobra el último día de febrero.
    """
    last_day_of_month = _get_last_day_of_month(year, month)
    return min(lease_start_day, last_day_of_month)


def _should_notify_lease_today(lease: Lease, current_dt: datetime) -> bool:
    today = current_dt.date()

    if lease.ended_date is not None:
        return False

    start_date = lease.start_date.date()
    end_date = lease.end_date.date()

    if start_date >= today:
        return False

    if end_date <= today:
        return False                                                                                                                                                            

    expected_due_day = _get_payment_due_day_for_month(
        lease_start_day=start_date.day,
        year=today.year,
        month=today.month,
    )

    return today.day == expected_due_day


def notify_due_payments() -> dict[str, list[int]]:
    """
    Identifica leases activos que deben recibir notificación de cobro hoy
    y envía el correo al cliente asociado.
    """
    db = SessionLocal()
    current_dt = now_tz()

    notified_lease_ids: list[int] = []
    failed_lease_ids: list[int] = []

    try:
        leases = (
            db.query(Lease)
            .options(selectinload(Lease.client))
            .filter(Lease.ended_date.is_(None))
            .filter(Lease.start_date < current_dt)
            .filter(Lease.end_date > current_dt)
            .all()
        )

        for lease in leases:
            if not _should_notify_lease_today(lease, current_dt):
                continue

            client = lease.client

            email_id: Optional[str] = send_payment_due_notification(
                to_email=client.email,
                user_name=client.name,
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
    result = notify_due_payments()
    print(result)