"""Час: усе, що бачить людина, — за київським часом; у базі системні мітки — UTC."""
from __future__ import annotations

import datetime as dt
import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import config

log = logging.getLogger(__name__)

try:
    TZ = ZoneInfo(config.TIMEZONE)
except ZoneInfoNotFoundError:  # на деяких системах немає бази часових поясів
    log.warning("Часовий пояс %s не знайдено — використовую UTC+3. Встановіть пакет tzdata.", config.TIMEZONE)
    TZ = dt.timezone(dt.timedelta(hours=3))

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]


def utcnow() -> dt.datetime:
    """Поточний UTC без tzinfo (так зберігаємо в БД)."""
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def now_local() -> dt.datetime:
    """Поточний київський час без tzinfo."""
    return dt.datetime.now(TZ).replace(tzinfo=None)


def utc_to_local(value: dt.datetime) -> dt.datetime:
    return value.replace(tzinfo=dt.timezone.utc).astimezone(TZ).replace(tzinfo=None)


def local_to_utc(value: dt.datetime) -> dt.datetime:
    return value.replace(tzinfo=TZ).astimezone(dt.timezone.utc).replace(tzinfo=None)


def fmt_dt(value: dt.datetime) -> str:
    """15.10.2026, 12:00 (Чт)"""
    return f"{value:%d.%m.%Y, %H:%M} ({WEEKDAYS[value.weekday()]})"


def fmt_day(day: dt.date) -> str:
    today = now_local().date()
    if day == today:
        return f"Сьогодні · {day:%d.%m}"
    if day == today + dt.timedelta(days=1):
        return f"Завтра · {day:%d.%m}"
    return f"{WEEKDAYS[day.weekday()]} · {day:%d.%m}"


def in_message_window() -> bool:
    """Автоматичні повідомлення (нагадування, відгуки) — лише вдень, не вночі."""
    start, end = config.MESSAGE_WINDOW
    return start <= now_local().hour < end
