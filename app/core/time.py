from app.core.config import settings

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import calendar

def now_tz(timezone_name: str = settings.timezone) -> datetime:
    return  datetime.now(ZoneInfo(timezone_name))

def today_tz(timezone_name: str = settings.timezone) -> date:
    return now_tz(timezone_name).date()

def minutes_from_now(minutes: int, timezone: str = settings.timezone) -> datetime:
    return now_tz(timezone) + timedelta(minutes=minutes)

def ensure_tz(dt: datetime, timezone_name: str = settings.timezone) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ZoneInfo(timezone_name))
    return dt

def remove_tz(dt: datetime) -> datetime:
    if dt and dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt

def last_day_of_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]