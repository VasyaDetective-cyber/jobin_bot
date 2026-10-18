from __future__ import annotations

import datetime as dt
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
import texts
from callbacks import DateCB, DatePageCB, EditorCB, HistCB, NavCB, OrderCB, SlotCB, VacancyCB
from database import crud
from database.models import Order, User, async_session
from handlers import views
from helpers import client_label, editor_recipients, safe_send, send_many
from keyboards.admin_kb import editor_kb, editor_skip_kb, time_issue_kb
from keyboards.schedule_kb import available_days, dates_kb, slot_ok, slots_kb, slots_text
from keyboards.user_kb import back_to_main_kb
from states import EditorFSM, OrderFSM
from timeutil import fmt_day, fmt_dt, now_local

router = Router(name="vacancy")
STAFF = F.from_user.id.in_(config.STAFF_IDS)
ADMIN = F.from_user.id.in_(config.ADMIN_IDS)
MAX_VACANCY = 3500


def _role(callback: CallbackQuery, owner: User | None) -> str | None:
    if owner is not None and callback.from_user.id == owner.telegram_id:
        return "owner"
    if callback.from_user.id in config.ADMIN_IDS:
        return "admin"
    return None


async def _load(order_id: int) -> tuple[Order | None, User | None]:
    async with async_session() as session:
        order = await crud.get_order(session, order_id)
        user = await crud.get_user(session, order.user_id) if order else None
    return order, user


async def prompt_vacancy(target: CallbackQuery, state: FSMContext, order: Order) -> None:
    await state.clear()
    await state.set_state(OrderFSM.waiting_vacancy_text)
    await state.update_data(order_id=order.id)
    await views.reply_or_edit(target, texts.VACANCY_PROMPT, back_to_main_kb())
    await target.answer()


@router.message(OrderFSM.waiting_vacancy_text, F.text)
async def receive_vacancy(message: Message, state: FSMContext) -> None:
    order_id = (await state.get_data()).get("order_id")
    text = message.text.strip()
    if len(text) > MAX_VACANCY:
        await message.answer(texts.VACANCY_TOO_LONG.format(n=len(text)), reply_markup=back_to_main_kb())
        return
    order, user = await _load(order_id) if order_id else (None, None)
    if order is None or user is None or user.telegram_id != message.from_user.id or order.status not in ("confirmed", "awaiting_time"):
        await state.clear()
        await message.answer(texts.SESSION_EXPIRED, reply_markup=back_to_main_kb())
        return
    async with async_session() as session:
        await crud.set_vacancy_text(session, order.id, text)
    await state.clear()
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Все вірно, обираю час", callback_data=VacancyCB(action="ok", order_id=order.id))
    kb.button(text="✏️ Змінити текст", callback_data=VacancyCB(action="edit", order_id=order.id))
    kb.button(text="🏠 Меню", callback_data=NavCB(target="main_menu"))
    kb.adjust(1)
    await message.answer(texts.VACANCY_PREVIEW.format(text=escape(text)), reply_markup=kb.as_markup())


@router.message(OrderFSM.waiting_vacancy_text)
async def vacancy_not_text(message: Message) -> None:
    await message.answer(texts.VACANCY_NOT_TEXT, reply_markup=back_to_main_kb())


@router.callback_query(VacancyCB.filter(F.action == "edit"))
async def vacancy_edit(callback: CallbackQuery, callback_data: VacancyCB, state: FSMContext) -> None:
    order, user = await _load(callback_data.order_id)
    if order is None or _role(callback, user) != "owner" or order.status not in ("confirmed", "awaiting_time"):
        await callback.answer("Це замовлення вже недоступне для зміни", show_alert=True)
        return
    await prompt_vacancy(callback, state, order)


@router.callback_query(VacancyCB.filter(F.action == "ok"))
async def vacancy_ok(callback: CallbackQuery, callback_data: VacancyCB, state: FSMContext) -> None:
    order, user = await _load(callback_data.order_id)
    if order is None or _role(callback, user) != "owner" or order.status not in ("confirmed", "awaiting_time"):
        await callback.answer("Це замовлення вже недоступне для зміни", show_alert=True)
        return
    if not order.vacancy_text:
        await prompt_vacancy(callback, state, order)
        return
    async with async_session() as session:
        await crud.set_order_status(session, order.id, "awaiting_time")
    await state.clear()
    await show_dates(callback, order.id)


async def show_dates(target: CallbackQuery, order_id: int, page: int = 0, for_admin: bool = False, new_message: bool = False) -> None:
    now = now_local()
    text = texts.SCHEDULE_INTRO.format(slots=slots_text()) if available_days(now) else texts.SCHEDULE_NO_DAYS
    if for_admin:
        text = f"🛠 <b>Замовлення №{order_id}</b>\n\n" + text
    markup = dates_kb(order_id, page, now, for_admin)
    if new_message:
        await target.message.answer(text, reply_markup=markup)
    else:
        await views.reply_or_edit(target, text, markup)
    await target.answer()


@router.callback_query(DatePageCB.filter())
async def date_page(callback: CallbackQuery, callback_data: DatePageCB) -> None:
    order, user = await _load(callback_data.order_id)
    role = _role(callback, user)
    if order is None or role is None:
        await callback.answer("Недоступно", show_alert=True)
        return
    await show_dates(callback, order.id, callback_data.page, for_admin=role == "admin")


@router.callback_query(DateCB.filter())
async def date_chosen(callback: CallbackQuery, callback_data: DateCB) -> None:
    order, user = await _load(callback_data.order_id)
    role = _role(callback, user)
    if order is None or role is None:
        await callback.answer("Недоступно", show_alert=True)
        return
    day = dt.datetime.strptime(callback_data.d, "%Y%m%d").date()
    now = now_local()
    if not any(slot_ok(day, h, now) for h in config.SLOT_HOURS):
        await callback.answer("На цей день вільних слотів уже немає", show_alert=True)
        await show_dates(callback, order.id, 0, for_admin=role == "admin")
        return
    await views.reply_or_edit(
        callback,
        texts.SCHEDULE_PICK_TIME.format(day=fmt_day(day)),
        slots_kb(order.id, day, now, for_admin=role == "admin"),
    )
    await callback.answer()


@router.callback_query(SlotCB.filter())
async def slot_chosen(callback: CallbackQuery, callback_data: SlotCB, bot: Bot) -> None:
    order, user = await _load(callback_data.order_id)
    role = _role(callback, user)
    if order is None or role is None:
        await callback.answer("Недоступно", show_alert=True)
        return
    if not (order.status == "awaiting_time" or (order.status == "in_work" and role == "admin")):
        await callback.answer("Це замовлення вже заплановано", show_alert=True)
        return
    day = dt.datetime.strptime(callback_data.d, "%Y%m%d").date()
    if callback_data.h not in config.SLOT_HOURS or not slot_ok(day, callback_data.h, now_local()):
        await callback.answer("Цей час уже недоступний — оберіть інший", show_alert=True)
        await show_dates(callback, order.id, 0, for_admin=role == "admin")
        return

    when = dt.datetime.combine(day, dt.time(callback_data.h))
    await schedule_order(bot, order.id, when, by_admin=role == "admin")
    if role == "admin":
        await views.reply_or_edit(callback, f"✅ Для замовлення №{order.id} встановлено час: <b>{fmt_dt(when)}</b>. Клієнта й редактора повідомлено.", None)
    else:
        kb = InlineKeyboardBuilder()
        kb.button(text="🗂 Мої замовлення", callback_data=HistCB(page=0))
        kb.button(text="🏠 Меню", callback_data=NavCB(target="main_menu"))
        kb.adjust(1)
        await views.reply_or_edit(callback, texts.SCHEDULED_OK.format(when=fmt_dt(when)), kb.as_markup())
    await callback.answer()


async def schedule_order(bot: Bot, order_id: int, when: dt.datetime, by_admin: bool) -> None:
    async with async_session() as session:
        order = await crud.get_order(session, order_id)
        updated = order.status == "in_work"
        conflicts = await crud.get_slot_conflicts(session, when, order.id)
        await crud.set_publish_time(session, order.id, when, "in_work", "")
        order = await crud.get_order(session, order_id)
        user = await crud.get_user(session, order.user_id)

    await dispatch_to_editor(bot, order, user, conflicts, updated=updated)
    if conflicts:
        ids = ", ".join(f"№{c.id}" for c in conflicts)
        await notify_time_issue(
            bot, order, user, f"⚠️ Час <b>{fmt_dt(when)}</b> уже зайнятий замовленням {ids}. Узгодьте з клієнтом інший час."
        )
    if by_admin:
        await safe_send(bot, user.telegram_id, texts.SCHEDULE_CHANGED.format(when=fmt_dt(when)), back_to_main_kb())


@router.callback_query(OrderCB.filter(F.action == "admtime"), ADMIN)
async def admin_set_time(callback: CallbackQuery, callback_data: OrderCB) -> None:
    order, _ = await _load(callback_data.order_id)
    if order is None or order.status not in ("awaiting_time", "in_work"):
        await callback.answer("Для цього замовлення час уже не змінюється", show_alert=True)
        return
    await show_dates(callback, order.id, 0, for_admin=True, new_message=True)


def _editor_text(order: Order, user: User | None, conflicts: list[Order], updated: bool) -> str:
    when = f"<b>{fmt_dt(order.publish_at)}</b>" if order.publish_at else "час не встановлено"
    lines = [
        f"{'🔄 Оновлено · ' if updated else ''}📬 <b>Вакансія до публікації</b> · №{order.id}",
        "",
        f"🕒 {when}",
        f"👤 {client_label(user)}",
        "",
        "🛒 <b>Замовлено:</b>",
        escape(order.items_text or "—"),
    ]
    if conflicts:
        lines += ["", "⚠️ Цей час уже зайнятий замовленням " + ", ".join(f"№{c.id}" for c in conflicts) + " — менеджер узгодить інший."]
    lines += ["", "Текст вакансії — у повідомленні вище 👆"]
    return "\n".join(lines)


async def dispatch_to_editor(
    bot: Bot, order: Order, user: User | None, conflicts: list[Order], updated: bool = False, recipients: list[int] | None = None
) -> None:
    body = order.vacancy_text or "—"
    chunks = [body[i:i + 3900] for i in range(0, len(body), 3900)] or ["—"]
    for chat_id in recipients or editor_recipients():
        for n, chunk in enumerate(chunks):
            title = f"📄 <b>Текст вакансії · №{order.id}</b>\n\n" if n == 0 else ""
            await safe_send(bot, chat_id, f"{title}{escape(chunk)}")
        await safe_send(bot, chat_id, _editor_text(order, user, conflicts, updated), editor_kb(order.id))


async def notify_time_issue(bot: Bot, order: Order, user: User | None, reason: str) -> None:
    text = f"🕒 <b>Потрібне рішення щодо часу · №{order.id}</b>\n👤 {client_label(user)}\n\n{reason}"
    for admin_id in config.ADMIN_IDS:
        await safe_send(bot, admin_id, text, time_issue_kb(order.id))


@router.callback_query(OrderCB.filter(F.action == "card"), STAFF)
async def show_card(callback: CallbackQuery, callback_data: OrderCB, bot: Bot) -> None:
    order, user = await _load(callback_data.order_id)
    if order is None:
        await callback.answer("Не знайдено", show_alert=True)
        return
    await dispatch_to_editor(bot, order, user, [], recipients=[callback.from_user.id])
    await callback.answer()


@router.message(Command("queue"), STAFF)
async def cmd_queue(message: Message, state: FSMContext) -> None:
    await state.clear()
    text, markup = await views.queue_view(is_admin=message.from_user.id in config.ADMIN_IDS)
    await message.answer(text, reply_markup=markup)


@router.callback_query(EditorCB.filter(F.action == "busy"), STAFF)
async def editor_busy(callback: CallbackQuery, callback_data: EditorCB, bot: Bot) -> None:
    order, user = await _load(callback_data.order_id)
    if order is None or order.status != "in_work":
        await callback.answer("Це замовлення вже оброблено", show_alert=True)
        return
    async with async_session() as session:
        await crud.set_time_note(session, order.id, "conflict")
    await notify_time_issue(
        bot, order, user,
        f"⏰ Редактор повідомив, що час <b>{fmt_dt(order.publish_at) if order.publish_at else '—'}</b> зайнятий. "
        "Зв'яжіться з клієнтом і узгодьте інший час.",
    )
    await callback.message.edit_text(
        _editor_text(order, user, [], False) + "\n\n⏰ Передано менеджеру — очікуйте новий час.", reply_markup=None
    )
    await callback.answer("Менеджера повідомлено")


@router.callback_query(EditorCB.filter(F.action == "published"), STAFF)
async def editor_published(callback: CallbackQuery, callback_data: EditorCB, state: FSMContext) -> None:
    order, _ = await _load(callback_data.order_id)
    if order is None or order.status != "in_work":
        await callback.answer("Це замовлення вже оброблено", show_alert=True)
        return
    await state.clear()
    await state.set_state(EditorFSM.waiting_link)
    await state.update_data(order_id=order.id, chat_id=callback.message.chat.id, msg_id=callback.message.message_id)
    await callback.message.answer(
        "🔗 Надішліть посилання на опублікований пост — клієнт отримає його разом із подякою. "
        "Або натисніть «Пропустити».",
        reply_markup=editor_skip_kb(order.id),
    )
    await callback.answer()


async def finish_publish(bot: Bot, data: dict, link: str | None) -> bool:
    order_id = data.get("order_id")
    async with async_session() as session:
        order = await crud.get_order(session, order_id) if order_id else None
        if order is None or order.status != "in_work":
            return False
        await crud.mark_published(session, order.id, link)
        user = await crud.get_user(session, order.user_id)

    link_line = f"🔗 {escape(link)}\n" if link else ""
    kb = InlineKeyboardBuilder()
    kb.button(text="🔁 Повторити замовлення", callback_data=OrderCB(action="repeat", order_id=order.id))
    kb.button(text="🏠 Меню", callback_data=NavCB(target="main_menu"))
    kb.adjust(1)
    await safe_send(bot, user.telegram_id, texts.PUBLISHED.format(link=link_line), kb.as_markup(), disable_web_page_preview=False)
    try:
        await bot.edit_message_reply_markup(chat_id=data["chat_id"], message_id=data["msg_id"], reply_markup=None)
    except Exception:
        pass
    return True


@router.message(EditorFSM.waiting_link, F.text, STAFF)
async def editor_link(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    await state.clear()
    done = await finish_publish(bot, data, message.text.strip()[:1000])
    await message.answer("✅ Готово, клієнта повідомлено." if done else "Це замовлення вже оброблено.")


@router.callback_query(EditorCB.filter(F.action == "skip"), STAFF)
async def editor_skip(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    await state.clear()
    done = await finish_publish(bot, data, None)
    await callback.message.edit_text("✅ Готово, клієнта повідомлено." if done else "Це замовлення вже оброблено.")
    await callback.answer()