"""Екрани (текст + клавіатура), які використовують кілька хендлерів."""
from __future__ import annotations

from html import escape

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

import texts
from callbacks import AdmCB, HistCB, NavCB, OrderCB
from database import crud
from database.models import User, async_session
from helpers import client_label, status_label
from keyboards.user_kb import contact_chat_kb, main_menu_kb
from timeutil import fmt_dt, utc_to_local
from utils import fmt

PAGE = 5


async def reply_or_edit(target: Message | CallbackQuery, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    """Для кнопки — редагує поточне повідомлення, для тексту — надсилає нове."""
    if isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(text, reply_markup=markup)
        except TelegramBadRequest as exc:
            if "not modified" in str(exc):
                return
            await target.message.answer(text, reply_markup=markup)
    else:
        await target.answer(text, reply_markup=markup)


async def main_menu_view(user: User, greeting: str | None = None) -> tuple[str, InlineKeyboardMarkup]:
    async with async_session() as session:
        pending = await crud.get_pending_action_order(session, user.id)
    return greeting or texts.MENU_TEXT, main_menu_kb(pending)


async def contact_view(user: User) -> tuple[str, InlineKeyboardMarkup]:
    async with async_session() as session:
        username = await crud.manager_username_for(session, user)
        return texts.CONTACT.format(who=f" @{escape(username)}"), contact_chat_kb(username)

async def history_view(user: User, page: int = 0) -> tuple[str, InlineKeyboardMarkup]:
    async with async_session() as session:
        total = await crud.count_user_orders(session, user.id)
        orders = await crud.get_user_orders(session, user.id, offset=page * PAGE, limit=PAGE)
        items = await crud.get_items_for_orders(session, [o.id for o in orders])

    kb = InlineKeyboardBuilder()
    if not orders:
        kb.button(text="🛒 Замовити розміщення", callback_data=NavCB(target="catalog"))
        kb.button(text="🏠 Меню", callback_data=NavCB(target="main_menu"))
        kb.adjust(1)
        return "🗂 У вас поки немає замовлень. Саме час оформити перше 😉", kb.as_markup()

    lines = [f"🗂 <b>Ваші замовлення</b> ({total})", ""]
    for o in orders:
        names = [i.name for i in items.get(o.id, []) if i.kind != "addon"] or [
            l.split(" — ")[0] for l in (o.items_text or "").splitlines() if l
        ]
        extra = f" +{len(names) - 1}" if len(names) > 1 else ""
        first = escape(names[0]) if names else "—"
        lines.append(
            f"<b>№{o.id}</b> · {utc_to_local(o.created_at):%d.%m.%Y} · {first}{extra} · {fmt(o.amount)} грн\n"
            f"   {status_label(o)}"
        )
        if o.status == "pending_payment":
            kb.button(text=f"💳 Оплатити №{o.id}", callback_data=OrderCB(action="pay", order_id=o.id))
        elif o.status == "confirmed":
            kb.button(text=f"📝 Додати вакансію №{o.id}", callback_data=OrderCB(action="vacancy", order_id=o.id))
        elif o.status == "awaiting_time":
            kb.button(text=f"🕒 Обрати час №{o.id}", callback_data=OrderCB(action="schedule", order_id=o.id))
        elif o.status in ("published", "in_work", "rejected"):
            kb.button(text=f"🔁 Повторити №{o.id}", callback_data=OrderCB(action="repeat", order_id=o.id))
    kb.adjust(1)

    nav = InlineKeyboardBuilder()
    if page > 0:
        nav.button(text="⬅️", callback_data=HistCB(page=page - 1))
    if (page + 1) * PAGE < total:
        nav.button(text="➡️", callback_data=HistCB(page=page + 1))
    if nav.buttons:
        nav.adjust(2)
        kb.attach(nav)
    foot = InlineKeyboardBuilder()
    foot.button(text="🛒 Замовити ще", callback_data=NavCB(target="catalog"))
    foot.button(text="🏠 Меню", callback_data=NavCB(target="main_menu"))
    foot.adjust(1)
    kb.attach(foot)
    return "\n".join(lines), kb.as_markup()


async def queue_view(is_admin: bool = True) -> tuple[str, InlineKeyboardMarkup]:
    """Черга публікацій для редактора та адмінів."""
    async with async_session() as session:
        orders = await crud.get_queue(session)
        users = {o.user_id: await crud.get_user(session, o.user_id) for o in orders}
    kb = InlineKeyboardBuilder()
    close = AdmCB(section="home") if is_admin else NavCB(target="main_menu")
    if not orders:
        kb.button(text="↩️ Закрити", callback_data=close)
        return "📋 Черга порожня — усе опубліковано 🎉", kb.as_markup()
    lines = ["📋 <b>Черга публікацій</b>", ""]
    for o in orders[:15]:
        when = fmt_dt(o.publish_at) if o.publish_at else "час не встановлено"
        u = users.get(o.user_id)
        who = f"@{u.username}" if u and u.username else (str(u.telegram_id) if u else "—")
        lines.append(f"🕒 {when} · №{o.id} · {escape(who)}")
        kb.button(text=f"📄 №{o.id} · {when[:16]}", callback_data=OrderCB(action="card", order_id=o.id))
    kb.button(text="↩️ Закрити", callback_data=close)
    kb.adjust(1)
    return "\n".join(lines), kb.as_markup()