"""
Tests para email_schedules_worker.py.

Estos tests usan fakes/mocks:
- No requieren una base de datos real.
- No envían correos reales (se mockea worker.send_email).
- Validan los helpers de fechas, la creación de EmailScheduleRuns,
  el envío inline y el dispatch del worker por trigger_type.

Ejecutar:
    pytest -q app/tests/jobs/test_email_schedules_worker.py
"""

import importlib
import os
from datetime import date, datetime, timedelta

import pytest


MODULE_PATH = os.getenv(
    "EMAIL_SCHEDULES_WORKER_MODULE",
    "app.jobs.email_schedules_worker",
)

worker = importlib.import_module(MODULE_PATH)


class Obj:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeColumn:
    """Permite construir expresiones tipo EmailScheduleRuns.scheduled_for == x."""

    def __init__(self, name):
        self.name = name

    def __eq__(self, other):
        return ("eq", self.name, other)

    def is_(self, other):
        return ("is", self.name, other)

    def isnot(self, other):
        return ("isnot", self.name, other)

    def in_(self, other):
        return ("in", self.name, other)


class FakeRun:
    """Reemplaza a EmailScheduleRuns. Solo los campos que el worker usa hoy."""

    schedule_id = FakeColumn("schedule_id")
    lease_id = FakeColumn("lease_id")
    scheduled_for = FakeColumn("scheduled_for")
    status = FakeColumn("status")

    def __init__(
        self,
        schedule_id=None,
        lease_id=None,
        scheduled_for=None,
        status="pending",
        sent_at=None,
        failed_at=None,
        error_message=None,
        **kwargs,
    ):
        self.schedule_id = schedule_id
        self.lease_id = lease_id
        self.scheduled_for = scheduled_for
        self.status = status
        self.sent_at = sent_at
        self.failed_at = failed_at
        self.error_message = error_message

        for key, value in kwargs.items():
            setattr(self, key, value)


class FakeQuery:
    """
    Query falsa. Aplica únicamente los filtros generados por FakeColumn
    (tuplas tipo ("eq", name, value)), usados para EmailScheduleRuns. Los
    filtros de Lease/User son expresiones reales de SQLAlchemy y se ignoran.
    """

    def __init__(self, data):
        self.data = data
        self.conditions = []

    def join(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        self.conditions.extend(args)
        return self

    def _matches(self, item):
        for cond in self.conditions:
            if isinstance(cond, tuple) and len(cond) == 3 and cond[0] == "eq":
                _, name, value = cond
                if getattr(item, name, None) != value:
                    return False
        return True

    def _filtered(self):
        return [item for item in self.data if self._matches(item)]

    def all(self):
        return list(self._filtered())

    def first(self):
        results = self._filtered()
        return results[0] if results else None


class FakeDB:
    def __init__(self, worker_module, *, leases=None, users=None, runs=None, schedules=None):
        self.worker_module = worker_module
        self.leases = leases or []
        self.users = users or []
        self.runs = runs or []
        self.schedules = schedules or []

        self.added = []
        self.commits = 0
        self.closed = False

    def query(self, model):
        name = getattr(model, "__name__", "")

        if model is self.worker_module.Lease or name == "Lease":
            return FakeQuery(self.leases)

        if model is self.worker_module.User or name == "User":
            return FakeQuery(self.users)

        if model is self.worker_module.EmailSchedules or name == "EmailSchedules":
            return FakeQuery(self.schedules)

        if model is self.worker_module.EmailScheduleRuns or name in {"EmailScheduleRuns", "FakeRun"}:
            return FakeQuery(self.runs)

        return FakeQuery([])

    def add(self, obj):
        self.added.append(obj)
        if isinstance(obj, FakeRun):
            self.runs.append(obj)

    def commit(self):
        self.commits += 1

    def refresh(self, obj):
        pass

    def close(self):
        self.closed = True


def make_schedule(**overrides):
    data = {
        "id": 1,
        "status": "active",
        "deleted_at": None,
        "trigger_type": "relative_to_payment_due",
        "offset_days": 0,
        "to": ["*"],
        "subject": "Asunto de prueba",
        "body": "Cuerpo de prueba",
        "attachments": [],
        "scheduled_for": None,
    }
    data.update(overrides)
    return Obj(**data)


def make_lease(**overrides):
    client_email = overrides.pop("client_email", "cliente@example.com")
    data = {
        "id": 100,
        "client_id": 200,
        "start_date": datetime(2026, 5, 21, 0, 0, 0),
        "end_date": datetime(2026, 9, 21, 0, 0, 0),
        "ended_date": None,
        "client": Obj(email=client_email),
    }
    data.update(overrides)
    return Obj(**data)


def make_user(**overrides):
    data = {
        "id": 200,
        "role": "client",
        "email": "cliente@example.com",
        "deleted_at": None,
    }
    data.update(overrides)
    return Obj(**data)


@pytest.fixture(autouse=True)
def patch_email_schedule_runs_model(monkeypatch):
    """Evita crear instancias reales de SQLAlchemy en los tests unitarios."""
    monkeypatch.setattr(worker, "EmailScheduleRuns", FakeRun)


@pytest.fixture
def capture_send_email(monkeypatch):
    """Mockea worker.send_email y captura los payloads enviados."""
    payloads = []

    def fake_send_email(**kwargs):
        payloads.append(kwargs)

    monkeypatch.setattr(worker, "send_email", fake_send_email, raising=False)
    return payloads


# ---------------------------------------------------------------------------
# get_payment_notice_dates
# ---------------------------------------------------------------------------

def test_get_payment_notice_dates_after_payment_due_skips_first_and_last():
    result = worker.get_payment_notice_dates(
        datetime(2026, 5, 21),
        datetime(2026, 9, 21),
        4,
    )
    assert result == [
        date(2026, 6, 25),
        date(2026, 7, 25),
        date(2026, 8, 25),
    ]


def test_get_payment_notice_dates_large_offset_can_move_to_next_month():
    result = worker.get_payment_notice_dates(
        datetime(2026, 5, 21),
        datetime(2026, 9, 21),
        11,
    )
    assert result == [
        date(2026, 7, 2),
        date(2026, 8, 1),
        date(2026, 9, 1),
    ]


def test_get_payment_notice_dates_before_payment_due_with_negative_offset():
    result = worker.get_payment_notice_dates(
        datetime(2026, 5, 21),
        datetime(2026, 9, 21),
        -4,
    )
    assert result == [
        date(2026, 6, 17),
        date(2026, 7, 17),
        date(2026, 8, 17),
    ]


def test_get_payment_notice_dates_handles_short_months():
    result = worker.get_payment_notice_dates(
        datetime(2026, 1, 31),
        datetime(2026, 5, 31),
        2,
    )
    assert result == [
        date(2026, 3, 2),   # 2026-02-28 + 2 días
        date(2026, 4, 2),   # 2026-03-31 + 2 días
        date(2026, 5, 2),   # 2026-04-30 + 2 días
    ]


def test_get_payment_notice_dates_returns_empty_when_end_date_is_not_after_start_date():
    assert worker.get_payment_notice_dates(datetime(2026, 5, 21), datetime(2026, 5, 21), 3) == []
    assert worker.get_payment_notice_dates(datetime(2026, 5, 21), datetime(2026, 5, 20), 3) == []


# ---------------------------------------------------------------------------
# calculate_due_recurring_scheduled_for  (el intervalo vive en offset_days)
# ---------------------------------------------------------------------------

def test_calculate_due_recurring_scheduled_for_returns_none_before_start_date():
    schedule = make_schedule(scheduled_for=date(2026, 5, 21), offset_days=7)
    result = worker.calculate_due_recurring_scheduled_for(schedule=schedule, today=date(2026, 5, 20))
    assert result is None


def test_calculate_due_recurring_scheduled_for_returns_start_date_on_first_day():
    schedule = make_schedule(scheduled_for=date(2026, 5, 21), offset_days=7)
    result = worker.calculate_due_recurring_scheduled_for(schedule=schedule, today=date(2026, 5, 21))
    assert result == date(2026, 5, 21)


def test_calculate_due_recurring_scheduled_for_returns_last_due_occurrence():
    schedule = make_schedule(scheduled_for=date(2026, 5, 21), offset_days=7)
    result = worker.calculate_due_recurring_scheduled_for(schedule=schedule, today=date(2026, 6, 5))
    assert result == date(2026, 6, 4)


def test_calculate_due_recurring_scheduled_for_returns_none_when_interval_is_invalid():
    schedule = make_schedule(scheduled_for=date(2026, 5, 21), offset_days=0)
    # offset_days=0 se considera intervalo inválido -> None (el router exige > 0).
    result = worker.calculate_due_recurring_scheduled_for(schedule=schedule, today=date(2026, 6, 5))
    assert result is None


def test_calculate_due_recurring_scheduled_for_uses_default_interval_one_day():
    schedule = make_schedule(scheduled_for=date(2026, 5, 21), offset_days=None)
    result = worker.calculate_due_recurring_scheduled_for(schedule=schedule, today=date(2026, 5, 23))
    assert result == date(2026, 5, 23)


def test_calculate_due_recurring_scheduled_for_returns_none_without_scheduled_for():
    schedule = make_schedule(scheduled_for=None, offset_days=7)
    result = worker.calculate_due_recurring_scheduled_for(schedule=schedule, today=date(2026, 6, 5))
    assert result is None


# ---------------------------------------------------------------------------
# process_relative_to_payment_due  (envío inline)
# ---------------------------------------------------------------------------

def test_process_relative_to_payment_due_sends_when_today_is_due(capture_send_email):
    lease = make_lease(start_date=datetime(2026, 5, 21), end_date=datetime(2026, 9, 21))
    schedule = make_schedule(offset_days=4)
    db = FakeDB(worker, leases=[lease], users=[make_user()])

    worker.process_relative_to_payment_due(db=db, schedule=schedule, today=date(2026, 6, 25))

    assert len(db.runs) == 1
    run = db.runs[0]
    assert run.schedule_id == schedule.id
    assert run.lease_id == lease.id
    assert run.scheduled_for == date(2026, 6, 25)
    assert run.status == "sent"
    assert run.sent_at is not None
    assert len(capture_send_email) == 1
    assert capture_send_email[0]["to"] == "cliente@example.com"


def test_process_relative_to_payment_due_does_nothing_when_today_is_not_due(capture_send_email):
    lease = make_lease(start_date=datetime(2026, 5, 21), end_date=datetime(2026, 9, 21))
    schedule = make_schedule(offset_days=4)
    db = FakeDB(worker, leases=[lease], users=[make_user()])

    worker.process_relative_to_payment_due(db=db, schedule=schedule, today=date(2026, 6, 26))

    assert db.runs == []
    assert capture_send_email == []


def test_process_relative_to_payment_due_skips_existing_sent_run(capture_send_email):
    lease = make_lease(start_date=datetime(2026, 5, 21), end_date=datetime(2026, 9, 21))
    existing_run = FakeRun(
        schedule_id=1, lease_id=lease.id, scheduled_for=date(2026, 6, 25), status="sent"
    )
    schedule = make_schedule(id=1, offset_days=4)
    db = FakeDB(worker, leases=[lease], users=[make_user()], runs=[existing_run])

    worker.process_relative_to_payment_due(db=db, schedule=schedule, today=date(2026, 6, 25))

    assert len(db.runs) == 1
    assert capture_send_email == []


def test_process_relative_to_payment_due_retries_existing_failed_run(capture_send_email):
    lease = make_lease(start_date=datetime(2026, 5, 21), end_date=datetime(2026, 9, 21))
    existing_run = FakeRun(
        schedule_id=1, lease_id=lease.id, scheduled_for=date(2026, 6, 25), status="failed"
    )
    schedule = make_schedule(id=1, offset_days=4)
    db = FakeDB(worker, leases=[lease], users=[make_user()], runs=[existing_run])

    worker.process_relative_to_payment_due(db=db, schedule=schedule, today=date(2026, 6, 25))

    assert len(db.runs) == 1
    assert existing_run.status == "sent"
    assert len(capture_send_email) == 1


def test_process_relative_to_payment_due_marks_failed_when_send_raises(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("SMTP no disponible")

    monkeypatch.setattr(worker, "send_email", boom, raising=False)

    lease = make_lease(start_date=datetime(2026, 5, 21), end_date=datetime(2026, 9, 21))
    schedule = make_schedule(offset_days=4)
    db = FakeDB(worker, leases=[lease], users=[make_user()])

    worker.process_relative_to_payment_due(db=db, schedule=schedule, today=date(2026, 6, 25))

    assert len(db.runs) == 1
    run = db.runs[0]
    assert run.status == "failed"
    assert run.failed_at is not None
    assert "SMTP no disponible" in run.error_message


# ---------------------------------------------------------------------------
# process_relative_to_lease_start_date_schedule
# ---------------------------------------------------------------------------

def test_process_relative_to_lease_start_creates_run(capture_send_email):
    lease = make_lease(start_date=datetime(2026, 5, 21))
    schedule = make_schedule(trigger_type="relative_to_lease_start", offset_days=3)
    db = FakeDB(worker, leases=[lease], users=[make_user()])

    worker.process_relative_to_lease_start_date_schedule(
        db=db, schedule=schedule, today=date(2026, 5, 24)
    )

    assert len(db.runs) == 1
    assert db.runs[0].scheduled_for == date(2026, 5, 24)
    assert db.runs[0].status == "sent"
    assert len(capture_send_email) == 1


def test_process_relative_to_lease_start_does_nothing_before_due_date(capture_send_email):
    lease = make_lease(start_date=datetime(2026, 5, 21))
    schedule = make_schedule(trigger_type="relative_to_lease_start", offset_days=3)
    db = FakeDB(worker, leases=[lease], users=[make_user()])

    worker.process_relative_to_lease_start_date_schedule(
        db=db, schedule=schedule, today=date(2026, 5, 23)
    )

    assert db.runs == []
    assert capture_send_email == []


# ---------------------------------------------------------------------------
# process_relative_to_lease_end_date_schedule
# ---------------------------------------------------------------------------

def test_process_relative_to_lease_end_creates_run(capture_send_email):
    lease = make_lease(end_date=datetime(2026, 9, 21, 0, 0, 0))
    schedule = make_schedule(trigger_type="relative_to_lease_end", offset_days=7)
    db = FakeDB(worker, leases=[lease], users=[make_user()])

    worker.process_relative_to_lease_end_date_schedule(
        db=db, schedule=schedule, today=date(2026, 9, 14)
    )

    assert len(db.runs) == 1
    assert db.runs[0].scheduled_for == date(2026, 9, 14)
    assert db.runs[0].status == "sent"
    assert len(capture_send_email) == 1


# ---------------------------------------------------------------------------
# process_specific_date_schedule
# ---------------------------------------------------------------------------

def test_process_specific_date_creates_run_for_each_lease_and_completes(capture_send_email):
    leases = [make_lease(id=101, client_id=201), make_lease(id=102, client_id=202)]
    schedule = make_schedule(trigger_type="specific_date", scheduled_for=date(2026, 6, 1))
    db = FakeDB(worker, leases=leases, users=[make_user()])

    worker.process_specific_date_schedule(db=db, schedule=schedule, today=date(2026, 6, 1))

    assert len(db.runs) == 2
    assert [run.lease_id for run in db.runs] == [101, 102]
    assert all(run.scheduled_for == date(2026, 6, 1) for run in db.runs)
    assert len(capture_send_email) == 2
    assert schedule.status == "completed"


def test_process_specific_date_marks_failed_on_send_failure(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("SMTP no disponible")

    monkeypatch.setattr(worker, "send_email", boom, raising=False)

    leases = [make_lease(id=101, client_id=201)]
    schedule = make_schedule(trigger_type="specific_date", scheduled_for=date(2026, 6, 1))
    db = FakeDB(worker, leases=leases, users=[make_user()])

    worker.process_specific_date_schedule(db=db, schedule=schedule, today=date(2026, 6, 1))

    assert db.runs[0].status == "failed"
    # The API accepts failed as the terminal error status for schedules.
    assert schedule.status == "failed"
    assert db.runs[0].failed_at is not None
    assert db.runs[0].error_message == "SMTP no disponible"


def test_process_specific_date_marks_failed_if_only_one_send_fails(monkeypatch):
    attempts = []

    def send_with_one_failure(**kwargs):
        attempts.append(kwargs["to"])
        if kwargs["to"] == "failure@example.com":
            raise RuntimeError("Fixture delivery failure")

    monkeypatch.setattr(worker, "send_email", send_with_one_failure)
    leases = [
        make_lease(id=101, client_id=201, client_email="failure@example.com"),
        make_lease(id=102, client_id=202, client_email="success@example.com"),
    ]
    schedule = make_schedule(trigger_type="specific_date", scheduled_for=date(2026, 6, 1))
    db = FakeDB(worker, leases=leases)

    worker.process_specific_date_schedule(db=db, schedule=schedule, today=date(2026, 6, 1))

    assert attempts == ["failure@example.com", "success@example.com"]
    assert [run.status for run in db.runs] == ["failed", "sent"]
    assert db.runs[0].error_message == "Fixture delivery failure"
    assert db.runs[1].sent_at is not None
    assert schedule.status == "failed"


def test_process_specific_date_completes_with_no_recipients(capture_send_email):
    schedule = make_schedule(trigger_type="specific_date", scheduled_for=date(2026, 6, 1))
    db = FakeDB(worker, leases=[], users=[make_user()])

    worker.process_specific_date_schedule(db=db, schedule=schedule, today=date(2026, 6, 1))

    assert db.runs == []
    assert capture_send_email == []
    assert schedule.status == "completed"


def test_process_specific_date_does_nothing_before_scheduled_for(capture_send_email):
    schedule = make_schedule(trigger_type="specific_date", scheduled_for=date(2026, 6, 1))
    db = FakeDB(worker, leases=[make_lease()], users=[make_user()])

    worker.process_specific_date_schedule(db=db, schedule=schedule, today=date(2026, 5, 31))

    assert db.runs == []
    assert capture_send_email == []
    assert schedule.status == "active"  # intacto: aún no es su fecha


# ---------------------------------------------------------------------------
# process_recurring_schedule
# ---------------------------------------------------------------------------

def test_process_recurring_creates_run_for_due_occurrence(capture_send_email):
    lease = make_lease(start_date=datetime(2026, 5, 1, 0, 0, 0), end_date=datetime(2026, 12, 31, 0, 0, 0))
    schedule = make_schedule(trigger_type="recurring", scheduled_for=date(2026, 5, 21), offset_days=7)
    db = FakeDB(worker, leases=[lease], users=[make_user()])

    worker.process_recurring_schedule(db=db, schedule=schedule, today=date(2026, 6, 4))

    assert len(db.runs) == 1
    assert db.runs[0].scheduled_for == date(2026, 6, 4)
    assert db.runs[0].status == "sent"
    assert len(capture_send_email) == 1


def test_process_recurring_does_nothing_before_schedule_start(capture_send_email):
    lease = make_lease(start_date=datetime(2026, 5, 1), end_date=datetime(2026, 12, 31))
    schedule = make_schedule(trigger_type="recurring", scheduled_for=date(2026, 5, 21), offset_days=7)
    db = FakeDB(worker, leases=[lease], users=[make_user()])

    worker.process_recurring_schedule(db=db, schedule=schedule, today=date(2026, 5, 20))

    assert db.runs == []
    assert capture_send_email == []


# ---------------------------------------------------------------------------
# email_schedules_worker  (dispatch por trigger_type)
# ---------------------------------------------------------------------------

def test_email_schedules_worker_dispatches_by_trigger_type_and_closes_db(monkeypatch):
    calls = []

    schedules = [
        make_schedule(id=1, trigger_type="relative_to_lease_start"),
        make_schedule(id=2, trigger_type="relative_to_lease_end"),
        make_schedule(id=3, trigger_type="relative_to_payment_due"),
        make_schedule(id=4, trigger_type="specific_date"),
        make_schedule(id=5, trigger_type="recurring"),
        make_schedule(id=6, trigger_type="unknown"),
    ]

    db = FakeDB(worker, schedules=schedules)

    monkeypatch.setattr(worker, "SessionLocal", lambda: db)
    monkeypatch.setattr(worker, "today_tz", lambda: date(2026, 6, 1))

    monkeypatch.setattr(
        worker, "process_relative_to_lease_start_date_schedule",
        lambda db, schedule, today: calls.append(("start", schedule.id, today)),
    )
    monkeypatch.setattr(
        worker, "process_relative_to_lease_end_date_schedule",
        lambda db, schedule, today: calls.append(("end", schedule.id, today)),
    )
    monkeypatch.setattr(
        worker, "process_relative_to_payment_due",
        lambda db, schedule, today: calls.append(("payment_due", schedule.id, today)),
    )
    monkeypatch.setattr(
        worker, "process_specific_date_schedule",
        lambda db, schedule, today: calls.append(("specific", schedule.id, today)),
    )
    monkeypatch.setattr(
        worker, "process_recurring_schedule",
        lambda db, schedule, today: calls.append(("recurring", schedule.id, today)),
    )

    worker.email_schedules_worker()

    assert calls == [
        ("start", 1, date(2026, 6, 1)),
        ("end", 2, date(2026, 6, 1)),
        ("payment_due", 3, date(2026, 6, 1)),
        ("specific", 4, date(2026, 6, 1)),
        ("recurring", 5, date(2026, 6, 1)),
    ]
    assert db.closed is True
