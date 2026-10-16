# tests/jobs/test_notify_payment_due.py

from datetime import datetime
from types import SimpleNamespace

from app.jobs.notify_payment_due import _should_notify_lease_today


def make_lease(
    *,
    start_date: datetime,
    end_date: datetime,
    ended_date=None,
):
    return SimpleNamespace(
        start_date=start_date,
        end_date=end_date,
        ended_date=ended_date,
    )


def test_should_notify_when_today_matches_start_day():
    lease = make_lease(
        start_date=datetime(2026, 1, 15, 10, 0),
        end_date=datetime(2026, 12, 15, 10, 0),
    )

    current_dt = datetime(2026, 5, 15, 9, 0)

    assert _should_notify_lease_today(lease, current_dt) is True


def test_should_not_notify_when_today_does_not_match_start_day():
    lease = make_lease(
        start_date=datetime(2026, 1, 15, 10, 0),
        end_date=datetime(2026, 12, 15, 10, 0),
    )

    current_dt = datetime(2026, 5, 14, 9, 0)

    assert _should_notify_lease_today(lease, current_dt) is False


def test_should_notify_on_last_day_when_start_day_is_31_and_month_has_30_days():
    lease = make_lease(
        start_date=datetime(2026, 1, 31, 10, 0),
        end_date=datetime(2026, 12, 31, 10, 0),
    )

    current_dt = datetime(2026, 4, 30, 9, 0)

    assert _should_notify_lease_today(lease, current_dt) is True


def test_should_notify_on_last_day_of_february_when_start_day_is_31():
    lease = make_lease(
        start_date=datetime(2026, 1, 31, 10, 0),
        end_date=datetime(2026, 12, 31, 10, 0),
    )

    current_dt = datetime(2026, 2, 28, 9, 0)

    assert _should_notify_lease_today(lease, current_dt) is True


def test_should_not_notify_when_lease_has_started_date():
    lease = make_lease(
        start_date=datetime(2026, 1, 15, 10, 0),
        end_date=datetime(2026, 12, 15, 10, 0),
        ended_date=datetime(2026, 5, 1, 10, 0),
    )

    current_dt = datetime(2026, 1, 15, 11, 0)

    assert _should_notify_lease_today(lease, current_dt) is False


def test_should_not_notify_when_lease_has_ended_date():
    lease = make_lease(
        start_date=datetime(2026, 1, 15, 10, 0),
        end_date=datetime(2026, 12, 15, 10, 0),
        ended_date=datetime(2026, 5, 1, 10, 0),
    )

    current_dt = datetime(2026, 5, 15, 9, 0)

    assert _should_notify_lease_today(lease, current_dt) is False