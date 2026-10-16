import calendar
from datetime import date, timedelta
from app.models.email_schedule_runs import EmailScheduleRuns
from app.models.email_schedules import EmailSchedules
from app.db.session import SessionLocal
from app.models.lease import Lease
from app.models.user import User
from app.services.email_service import send_email
from app.core.time import now_tz, today_tz
import logging

logger = logging.getLogger(__name__)


# HELPERS
def get_payment_notice_dates(start_date, end_date, offset_days = 0,) -> list:
    """
    Retorna todas las fechas en que se debe enviar un aviso de pago.

    Reglas:
    - El pago se repite el mismo día de start_date cada mes.
    - Si el mes no tiene ese día, se usa el último día del mes.
    - No se considera la primera fecha de pago.
    - No se considera la última fecha de pago relacionada con end_date.
    - offset_days indica cuántos días después de la fecha de pago se envía el aviso.

    Ejemplo:
    start_date = 2026-01-15
    end_date = 2026-06-15
    offset_days = 3

    Resultado:
    [
        date(2026, 2, 18),
        date(2026, 3, 18),
        date(2026, 4, 18),
        date(2026, 5, 18),
    ]
    """

    start_date = start_date.date()
    end_date = end_date.date()

    if not start_date or not end_date:
        return []

    if end_date <= start_date:
        return []

    notice_dates: list[date] = []

    payment_day = start_date.day

    def get_payment_due_date(year: int, month: int) -> date:
        last_day_of_month = calendar.monthrange(year, month)[1]
        valid_payment_day = min(payment_day, last_day_of_month)

        return date(year, month, valid_payment_day)

    def next_month(year: int, month: int) -> tuple[int, int]:
        if month == 12:
            return year + 1, 1

        return year, month + 1

    last_payment_due_date = get_payment_due_date(
        end_date.year,
        end_date.month,
    )

    year = start_date.year
    month = start_date.month

    while (year, month) <= (end_date.year, end_date.month):
        payment_due_date = get_payment_due_date(year, month)

        # Omite la primera fecha de pago.
        if payment_due_date <= start_date:
            year, month = next_month(year, month)
            continue

        # Omite la última fecha de pago relacionada con end_date.
        if payment_due_date >= last_payment_due_date:
            year, month = next_month(year, month)
            continue

        scheduled_for = payment_due_date + timedelta(days=offset_days)

        notice_dates.append(scheduled_for)

        year, month = next_month(year, month)

    return notice_dates


def calculate_due_recurring_scheduled_for(schedule, today):
    if not schedule.scheduled_for:
        return None

    interval_days = schedule.offset_days

    if interval_days is None:
        interval_days = 1

    if interval_days <= 0:
        return None

    start_date = schedule.scheduled_for

    # Todavía no llega la primera fecha de envío.
    if today < start_date:
        return None

    elapsed_days = (today - start_date).days

    occurrence_index = elapsed_days // interval_days

    scheduled_for = start_date + timedelta(
        days=occurrence_index * interval_days
    )

    return scheduled_for

# FUCTIONS
def process_relative_to_lease_start_date_schedule(db, schedule, today):
    offset_days = abs(schedule.offset_days or 0)

    query = (
        db.query(Lease)
        .join(User, Lease.client_id == User.id)
        .filter(User.deleted_at.is_(None))
        .filter(User.role == "client")
        .filter(User.email.isnot(None))
        .filter(Lease.ended_date.is_(None))
    )

    if schedule.to != ["*"]:
        query = query.filter(User.email.in_(schedule.to))

    leases = query.all()

    for lease in leases:
        if not lease.start_date:
            continue

        scheduled_for = lease.start_date.date() + timedelta(days=offset_days)

        if scheduled_for != today:
            continue

        existing_run = (
            db.query(EmailScheduleRuns)
            .filter(EmailScheduleRuns.schedule_id == schedule.id)
            .filter(EmailScheduleRuns.lease_id == lease.id)
            .filter(EmailScheduleRuns.scheduled_for == scheduled_for)
            .first()
        )

        if existing_run:
            continue

        run = EmailScheduleRuns(
            schedule_id=schedule.id,
            lease_id=lease.id,
            scheduled_for=scheduled_for,
            status="pending",
        )

        db.add(run)
        db.commit()
        db.refresh(run)

        try:
            send_email(
                to=lease.client.email,
                subject=schedule.subject,
                body=schedule.body,
                attachments=schedule.attachments,
            )

            run.status = "sent"
            run.sent_at = now_tz()

        except Exception as e:
            run.status = "failed"
            run.failed_at = now_tz()
            run.error_message = str(e)

        db.commit()


def process_relative_to_lease_end_date_schedule(db, schedule, today):
    offset_days = abs(schedule.offset_days or 0)

    query = (
        db.query(Lease)
        .join(User, Lease.client_id == User.id)
        .filter(User.deleted_at.is_(None))
        .filter(User.role == "client")
        .filter(User.email.isnot(None))
        .filter(Lease.ended_date.is_(None))
    )

    if schedule.to != ["*"]:
        query = query.filter(User.email.in_(schedule.to))

    leases = query.all()

    for lease in leases:
        if not lease.end_date:
            continue

        scheduled_for = lease.end_date.date() - timedelta(days=offset_days)

        if scheduled_for != today:
            continue

        existing_run = (
            db.query(EmailScheduleRuns)
            .filter(EmailScheduleRuns.schedule_id == schedule.id)
            .filter(EmailScheduleRuns.lease_id == lease.id)
            .filter(EmailScheduleRuns.scheduled_for == scheduled_for)
            .first()
        )

        if existing_run:
            continue

        run = EmailScheduleRuns(
            schedule_id=schedule.id,
            lease_id=lease.id,
            scheduled_for=scheduled_for,
            status="pending",
        )

        db.add(run)
        db.commit()
        db.refresh(run)
        
        try:
            send_email(
                to=lease.client.email,
                subject=schedule.subject,
                body=schedule.body,
                attachments=schedule.attachments,
            )

            run.status = "sent"
            run.sent_at = now_tz()

        except Exception as e:
            run.status = "failed"
            run.failed_at = now_tz()
            run.error_message = str(e)

        db.commit()


def process_specific_date_schedule(db, schedule, today):
    scheduled_for = schedule.scheduled_for

    if scheduled_for != today:
        return

    query = (
        db.query(Lease)
        .join(User, Lease.client_id == User.id)
        .filter(User.deleted_at.is_(None))
        .filter(User.role == "client")
        .filter(User.email.isnot(None))
        .filter(Lease.ended_date.is_(None))
    )

    if schedule.to != ["*"]:
        query = query.filter(User.email.in_(schedule.to))

    leases = query.all()

    had_failure = False

    for lease in leases:
        existing_run = (
            db.query(EmailScheduleRuns)
            .filter(EmailScheduleRuns.schedule_id == schedule.id)
            .filter(EmailScheduleRuns.lease_id == lease.id)
            .filter(EmailScheduleRuns.scheduled_for == scheduled_for)
            .first()
        )

        if existing_run:
            if existing_run.status != "sent":
                had_failure = True
            continue

        run = EmailScheduleRuns(
            schedule_id=schedule.id,
            lease_id=lease.id,
            scheduled_for=scheduled_for,
            status="pending",
        )

        db.add(run)
        db.commit()
        db.refresh(run)

        try:
            send_email(
                to=lease.client.email,
                subject=schedule.subject,
                body=schedule.body,
                attachments=schedule.attachments,
            )

            run.status = "sent"
            run.sent_at = now_tz()

        except Exception as e:
            run.status = "failed"
            run.failed_at = now_tz()
            run.error_message = str(e)
            had_failure = True

        db.commit()

    # specific_date es un disparo único: al terminar la fecha pasa a un estado
    # terminal para no volver a procesarse en corridas posteriores.
    schedule.status = "failed" if had_failure else "completed"
    db.commit()


def process_recurring_schedule(db, schedule, today):
    scheduled_for = calculate_due_recurring_scheduled_for(
        schedule=schedule,
        today=today,
    )

    if not scheduled_for:
        return

    query = (
        db.query(Lease)
        .join(User, Lease.client_id == User.id)
        .filter(User.deleted_at.is_(None))
        .filter(User.role == "client")
        .filter(User.email.isnot(None))
        .filter(Lease.ended_date.is_(None))
    )

    if schedule.to != ["*"]:
        query = query.filter(User.email.in_(schedule.to))

    leases = query.all()

    for lease in leases:
        # Opcional: evitar enviar si el contrato aún no comienza
        if lease.start_date and today < lease.start_date.date():
            continue

        # Opcional: evitar enviar después del término del contrato
        if lease.end_date and scheduled_for > lease.end_date.date():
            continue

        existing_run = (
            db.query(EmailScheduleRuns)
            .filter(EmailScheduleRuns.schedule_id == schedule.id)
            .filter(EmailScheduleRuns.lease_id == lease.id)
            .filter(EmailScheduleRuns.scheduled_for == scheduled_for)
            .first()
        )

        if existing_run:
            if existing_run.status == "sent":
                continue

            run = existing_run
        else:
            run = EmailScheduleRuns(
                schedule_id=schedule.id,
                lease_id=lease.id,
                scheduled_for=scheduled_for,
                status="pending",
            )

            db.add(run)
            db.commit()
            db.refresh(run)

        try:
            send_email(
                to=lease.client.email,
                subject=schedule.subject,
                body=schedule.body,
                attachments=schedule.attachments,
            )

            run.status = "sent"
            run.sent_at = now_tz()

        except Exception as e:
            run.status = "failed"
            run.failed_at = now_tz()
            run.error_message = str(e)

        db.commit()


def process_relative_to_payment_due(db, schedule, today):
    offset_days = schedule.offset_days or 0
    
    query = (
        db.query(Lease)
        .join(User, Lease.client_id == User.id)
        .filter(User.deleted_at.is_(None))
        .filter(User.role == "client")
        .filter(User.email.isnot(None))
        .filter(Lease.ended_date.is_(None))
        .filter(Lease.start_date.isnot(None))
        .filter(Lease.end_date.isnot(None))
    )

    if schedule.to != ["*"]:
        query = query.filter(User.email.in_(schedule.to))

    leases = query.all()

    for lease in leases:

        scheduled_dates = get_payment_notice_dates(lease.start_date, lease.end_date, offset_days)
        
        if today not in scheduled_dates:
            continue

        existing_run = (
            db.query(EmailScheduleRuns)
            .filter(EmailScheduleRuns.schedule_id == schedule.id)
            .filter(EmailScheduleRuns.lease_id == lease.id)
            .filter(EmailScheduleRuns.scheduled_for == today)
            .first()
        )

        if existing_run:
            if existing_run.status == "sent":
                continue

            run = existing_run
        else:
            run = EmailScheduleRuns(
                schedule_id=schedule.id,
                lease_id=lease.id,
                scheduled_for=today,
                status="pending",
            )

            db.add(run)
            db.commit()
            db.refresh(run)

        try:
            send_email(
                to=lease.client.email,
                subject=schedule.subject,
                body=schedule.body,
                attachments=schedule.attachments,
            )

            run.status = "sent"
            run.sent_at = now_tz()

        except Exception as e:
            run.status = "failed"
            run.failed_at = now_tz()
            run.error_message = str(e)

        db.commit()


# MAIN
def email_schedules_worker():
    db = SessionLocal()
    today = today_tz()

    try:
        schedules = (
            db.query(EmailSchedules)
            .filter(EmailSchedules.status == "active")
            .filter(EmailSchedules.deleted_at.is_(None))
            .all()
        )

        for schedule in schedules:

            if schedule.trigger_type == "relative_to_lease_start":
                process_relative_to_lease_start_date_schedule(
                    db=db,
                    schedule=schedule,
                    today=today,
                )
            
            elif schedule.trigger_type == "relative_to_lease_end":
                process_relative_to_lease_end_date_schedule(
                    db=db,
                    schedule=schedule,
                    today=today,
                )

            elif schedule.trigger_type == "relative_to_payment_due":
                process_relative_to_payment_due(
                    db=db,
                    schedule=schedule,
                    today=today,
                )

            elif schedule.trigger_type == "specific_date":
                process_specific_date_schedule(
                    db=db,
                    schedule=schedule,
                    today=today,
                )

            elif schedule.trigger_type == "recurring":
                process_recurring_schedule(
                    db=db,
                    schedule=schedule,
                    today=today,
                )
            
            else:
                pass

    finally:
        db.close()


if __name__ == "__main__":
    try:
        email_schedules_worker()
    except Exception:
        logger.exception("Error ejecutando el worker de correos programados.")
        raise