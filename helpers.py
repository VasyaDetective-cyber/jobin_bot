"""Спільні допоміжні функції для хендлерів."""
from __future__ import annotations

import logging
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardMarkup, Message

import config
from database import crud
from database.models import Order, User, async_session
from timeutil import fmt_dt
from utils import fmt

log = logging.getLogger(__name__)


def client_label(user: User | None) -> str:
    if user is None:
        return "—"
    name = escape(user.full_name or "клієнт")
    tag = f"@{escape(user.username)} · " if user.username else ""
    return f'<a href="tg://user?id={user.telegram_id}">{name}</a> {tag}ID <code>{user.telegram_id}</code>'


def status_label(order: Order) -> str:
    st = order.status
    if st == "pending_payment":
        return "⏳ Очікує оплати"
    if st == "pending_review":
        return "🔎 Перевіряємо оплату"
    if st == "confirmed":
        return "📝 Очікуємо текст вакансії"
    if st == "awaiting_time":
        return "🤝 Узгоджуємо час" if order.time_note == "discuss" else "🕒 Очікуємо вибір часу"
    if st == "in_work":
        when = f" на {fmt_dt(order.publish_at)}" if order.publish_at else ""
        return f"🚀 Заплановано{when}"
    if st == "published":
        return "✅ Опубліковано"
    if st == "rejected":
        return "❌ Відхилено"
    return st


def editor_recipients() -> list[int]:
    if config.EDITOR_ID:
        return [config.EDITOR_ID]
    log.warning("EDITOR_ID не задано — вакансії надсилаються всім адмінам.")
    return list(config.ADMIN_IDS)


async def safe_send(bot: Bot, chat_id: int, text: str, markup: InlineKeyboardMarkup | None = None, **kw) -> Message | None:
    """Надсилає повідомлення, не падаючи, якщо людина заблокувала бота."""
    try:
        return await bot.send_message(chat_id, text, reply_markup=markup, **kw)
    except TelegramForbiddenError:
        async with async_session() as session:
            await crud.mark_blocked(session, chat_id)
    except TelegramBadRequest as exc:
        log.warning("Не вдалося надіслати повідомлення %s: %s", chat_id, exc)
    except Exception:
        log.exception("Помилка надсилання повідомлення %s", chat_id)
    return None


async def send_many(bot: Bot, chat_ids: list[int], text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    for chat_id in chat_ids:
        await safe_send(bot, chat_id, text, markup, disable_web_page_preview=True)


def order_admin_caption(order: Order, user: User | None, manager_name: str | None) -> str:
    lines = [
        f"🆕 <b>Нове замовлення №{order.id}</b>",
        f"👤 {client_label(user)}",
        f"🧑‍💼 Менеджер: {escape(manager_name)}" if manager_name else "🧑‍💼 Менеджер: —",
        "",
        "🛒 <b>Склад:</b>",
        escape(order.items_text or "—"),
        "",
        f"💰 Сума: <b>{fmt(order.amount)} грн</b>",
    ]
    if order.discount_percent:
        lines.append(f"🏷 Знижка {fmt(order.discount_percent)}% (було {fmt(order.subtotal)} грн)")
    if order.pay_note:
        lines.append(f"🪙 Для довідки: {escape(order.pay_note)}")
    return "\n".join(lines)[:1000]


async def update_notifications(bot: Bot, order_id: int, status_line: str, markup: InlineKeyboardMarkup | None) -> None:
    """Після рішення одного адміна прибираємо кнопки «Підтвердити/Відхилити» в усіх інших."""
    async with async_session() as session:
        notes = await crud.get_notifications(session, order_id)
    for note in notes:
        try:
            await bot.edit_message_caption(
                chat_id=note.admin_id,
                message_id=note.message_id,
                caption=f"{note.caption}\n\n{status_line}"[:1024],
                reply_markup=markup,
            )
        except Exception as exc:  # повідомлення могли видалити — це не критично
            log.info("Не вдалося оновити повідомлення адміну %s: %s", note.admin_id, exc)