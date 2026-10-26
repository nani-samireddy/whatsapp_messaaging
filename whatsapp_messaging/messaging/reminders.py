"""Calendar-day reminder windows; no patient data or provider transport."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def date_window(instant, zone, days_before):
    days = int(days_before)
    if days != float(days_before) or not 0 <= days <= 30:
        raise ValueError('Start reminders must be between 0 and 30 whole days before the date.')
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    today = instant.astimezone(ZoneInfo(zone)).date()
    return today, today + timedelta(days=days)


def matches(value, instant, zone, days_before):
    if not value:
        return False
    value = value.date() if isinstance(value, datetime) else date.fromisoformat(str(value))
    start, end = date_window(instant, zone, days_before)
    return start <= value <= end


def daily_cron(value):
    parts = str(value or '').split(':')
    if len(parts) not in (2, 3):
        raise ValueError('Choose a reminder time, for example 09:00.')
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59) or (len(parts) == 3 and float(parts[2]) != 0):
        raise ValueError('Reminder time must use whole minutes.')
    return f'{minute} {hour} * * *'
