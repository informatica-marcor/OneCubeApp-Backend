# tests/jobs/test_notify_lease_ending_soon.py

from datetime import datetime
from types import SimpleNamespace

import app.jobs.notify_lease_ending_soon as job


def make_lease(
    *,
    lease_id: int = 1,
    start_date: datetime = datetime(2026, 1, 1, 10, 0),
    end_date: datetime,
    ended_date=None,
    email: str = "cliente@test.cl",
    name: str = "Cliente Test",
):
    return SimpleNamespace(
        id=lease_id,
        start_date=start_date,
        end_date=end_date,
        ended_date=ended_date,
        client=SimpleNamespace(
            email=email,
            name=name,
        ),
    )


def test_should_notify_when_lease_ends_in_15_days():
    lease = make_lease(
        lease_id=1,
        end_date=datetime(2026, 3, 10, 10, 0),
    )

    current_dt = datetime(2026, 2, 23, 9, 0)

    assert job._should_notify_lease_ending_soon_today(lease, current_dt) is True


def test_should_not_notify_when_lease_ends_in_14_days():
    lease = make_lease(
        lease_id=1,
        end_date=datetime(2026, 5, 29, 10, 0),
    )

    current_dt = datetime(2026, 5, 15, 9, 0)

    assert job._should_notify_lease_ending_soon_today(lease, current_dt) is False


def test_should_not_notify_when_lease_ends_in_16_days():
    lease = make_lease(
        lease_id=1,
        end_date=datetime(2026, 5, 31, 10, 0),
    )

    current_dt = datetime(2026, 5, 15, 9, 0)

    assert job._should_notify_lease_ending_soon_today(lease, current_dt) is False


def test_should_not_notify_when_lease_has_ended_date():
    lease = make_lease(
        lease_id=1,
        end_date=datetime(2026, 5, 30, 10, 0),
        ended_date=datetime(2026, 5, 10, 10, 0),
    )

    current_dt = datetime(2026, 5, 15, 9, 0)

    assert job._should_notify_lease_ending_soon_today(lease, current_dt) is False


def test_should_not_notify_when_end_date_is_today():
    lease = make_lease(
        lease_id=1,
        end_date=datetime(2026, 5, 15, 10, 0),
    )

    current_dt = datetime(2026, 5, 15, 9, 0)

    assert job._should_notify_lease_ending_soon_today(lease, current_dt) is False