"""Клавіатури вибору дати й часу публікації."""
from __future__ import annotations

import datetime as dt

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
from callbacks import AdmCB, DateCB, DatePageCB, NavCB, OrderCB, SlotCB
from timeutil import fmt_day

PAGE_SIZE = 6


def slot_ok(day: dt.date, hour: int, now: dt.datetime) -> bool:
    when = dt.datetime.combine(day, dt.time(hour))
    return when >= now + dt.timedelta(minutes=config.MIN_LEAD_MINUTES)


def available_days(now: dt.datetime) -> list[dt.date]:
    days = []
    for i in range(config.SCHEDULE_DAYS):
        day = now.date() + dt.timedelta(days=i)
        if any(slot_ok(day, h, now) for h in config.SLOT_HOURS):
            days.append(day)
    return days


def slots_text() -> str:
    return ", ".join(f"{h}:00" for h in config.SLOT_HOURS)


def _footer(kb: InlineKeyboardBuilder, order_id: int, for_admin: bool) -> None:
    if for_admin:
        kb.button(text="↩️ Закрити", callback_data=AdmCB(section="home"))
    else:
        kb.button(text="🤝 Обговорити час з менеджером", callback_data=OrderCB(action="discuss", order_id=order_id))
        kb.button(text="🏠 Меню", callback_data=NavCB(target="main_menu"))


def dates_kb(order_id: int, page: int, now: dt.datetime, for_admin: bool = False) -> InlineKeyboardMarkup:
    days = available_days(now)
    chunk = days[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    kb = InlineKeyboardBuilder()
    for day in chunk:
        kb.button(text=fmt_day(day), callback_data=DateCB(order_id=order_id, d=f"{day:%Y%m%d}"))
    kb.adjust(2)
    nav = InlineKeyboardBuilder()
    if page > 0:
        nav.button(text="⬅️ Раніше", callback_data=DatePageCB(order_id=order_id, page=page - 1))
    if (page + 1) * PAGE_SIZE < len(days):
        nav.button(text="Ще дати ➡️", callback_data=DatePageCB(order_id=order_id, page=page + 1))
    if nav.buttons:
        kb.attach(nav)
    foot = InlineKeyboardBuilder()
    _footer(foot, order_id, for_admin)
    foot.adjust(1)
    kb.attach(foot)
    return kb.as_markup()


def slots_kb(order_id: int, day: dt.date, now: dt.datetime, for_admin: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for hour in config.SLOT_HOURS:
        if slot_ok(day, hour, now):
            kb.button(text=f"{hour:02d}:00", callback_data=SlotCB(order_id=order_id, d=f"{day:%Y%m%d}", h=hour))
    kb.adjust(3)
    foot = InlineKeyboardBuilder()
    foot.button(text="⬅️ Інша дата", callback_data=DatePageCB(order_id=order_id, page=0))
    _footer(foot, order_id, for_admin)
    foot.adjust(1)
    kb.attach(foot)
    return kb.as_markup()