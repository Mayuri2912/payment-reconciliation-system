"""Business-day helpers. Assumption: only Saturday and Sunday are non-business days."""
import calendar
from datetime import date, timedelta


def is_business_day(day: date) -> bool:
    return day.weekday() < 5


def add_business_days(day: date, count: int) -> date:
    """Move forward `count` business days. A Saturday plus 1 business day is Monday."""
    current = day
    remaining = count
    while remaining > 0:
        current += timedelta(days=1)
        if is_business_day(current):
            remaining -= 1
    return current


def month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])
