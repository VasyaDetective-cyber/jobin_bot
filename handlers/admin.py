from __future__ import annotations

from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import CallbackQuery, Message

import config
import texts
import texts_extra as tx
from callbacks import AdmCB, OrderModerationCB
from database import crud
from database.models import User, async_session
from handlers import views
from helpers import safe_send, update_notifications
from keyboards.admin_kb import admin_main_kb, cancel_kb, reply_only_kb
from keyboards.user_kb import back_to_main_kb, chat_reply_kb, contact_manager_kb
from states import AdminChatFSM, AdminRejectFSM, OrderFSM
from utils import fmt

router = Router(name="admin")
router.message.filter(F.from_user.id.in_(config.ADMIN_IDS))
router.callback_query.filter(F.from_user.id.in_(config.ADMIN_IDS))


def _who(callback_or_message) -> str:
    u = callback_or_message.from_user
    return f"@{u.username}" if u.username else u.full_name


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("🛠 Адмін-панель JOBIN", reply_markup=admin_main_kb())


@router.callback_query(AdmCB.filter(F.section == "home"))
async def adm_home(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await views.reply_or_edit(callback, "🛠 Адмін-панель JOBIN", admin_main_kb())
    await callback.answer()


@router.callback_query(F.data == "admin_cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await views.reply_or_edit(callback, "🛠 Адмін-панель JOBIN", admin_main_kb())
    await callback.answer("Скасовано")


@router.callback_query(AdmCB.filter(F.section == "queue"))
async def adm_queue(callback: CallbackQuery) -> None:
    text, markup = await views.queue_view(is_admin=True)
    await views.reply_or_edit(callback, text, markup)
    await callback.answer()


@router.callback_query(OrderModerationCB.filter(F.action == "confirm"))
async def confirm_order(callback: CallbackQuery, callback_data: OrderModerationCB, bot: Bot, state: FSMContext) -> None:
    async with async_session() as session:
        order = await crud.get_order(session, callback_data.order_id)
        if order is None:
            await callback.answer("Замовлення не знайдено", show_alert=True)
            return
        if order.status != "pending_review":
            await callback.answer("Це замовлення вже оброблено іншим адміном", show_alert=True)
            return
        await crud.set_order_status(session, order.id, "confirmed")
        user = await crud.get_user(session, order.user_id)
        reward = await crud.grant_referral_reward(session, user)

    await update_notifications(bot, order.id, f"✅ Підтверджено · {escape(_who(callback))}", reply_only_kb(order.id))
    await callback.answer("Оплату підтверджено")

    key = StorageKey(bot_id=bot.id, chat_id=user.telegram_id, user_id=user.telegram_id)
    client_state = FSMContext(storage=state.storage, key=key)
    await client_state.clear()
    await client_state.set_state(OrderFSM.waiting_vacancy_text)
    await client_state.update_data(order_id=order.id)
    await safe_send(bot, user.telegram_id, texts.PAYMENT_CONFIRMED, back_to_main_kb())
    if reward:
        discount, referrer = reward
        await safe_send(bot, referrer.telegram_id, tx.REFERRAL_REWARD.format(percent=fmt(discount.percent)), back_to_main_kb())


@router.callback_query(OrderModerationCB.filter(F.action == "reject"))
async def reject_order_start(callback: CallbackQuery, callback_data: OrderModerationCB, state: FSMContext) -> None:
    async with async_session() as session:
        order = await crud.get_order(session, callback_data.order_id)
    if order is None or order.status != "pending_review":
        await callback.answer("Це замовлення вже оброблено іншим адміном", show_alert=True)
        return
    await state.clear()
    await state.update_data(reject_order_id=order.id)
    await state.set_state(AdminRejectFSM.waiting_reason)
    await callback.message.answer(
        "Напишіть причину відхилення (її побачить клієнт):", reply_markup=cancel_kb()
    )
    await callback.answer()


@router.message(AdminRejectFSM.waiting_reason, F.text)
async def reject_order_finish(message: Message, state: FSMContext, bot: Bot) -> None:
    order_id = (await state.get_data()).get("reject_order_id")
    reason = message.text.strip()
    await state.clear()
    async with async_session() as session:
        order = await crud.get_order(session, order_id)
        if order is None or order.status != "pending_review":
            await message.answer("Це замовлення вже оброблено іншим адміном.")
            return
        await crud.set_order_status(session, order.id, "rejected", reason=reason)
        await crud.release_order_benefits(session, order)
        user = await crud.get_user(session, order.user_id)
        username = await crud.manager_username_for(session, user)

    await update_notifications(bot, order.id, f"❌ Відхилено · {escape(_who(message))}\nПричина: {escape(reason)}", reply_only_kb(order.id))
    await message.answer("❌ Замовлення відхилено, клієнта повідомлено.", reply_markup=admin_main_kb())
    await safe_send(bot, user.telegram_id, texts.REJECTED.format(order_id=order.id, reason=escape(reason)), contact_manager_kb(username))


@router.callback_query(OrderModerationCB.filter(F.action == "reply"))
async def reply_start(callback: CallbackQuery, callback_data: OrderModerationCB, state: FSMContext) -> None:
    async with async_session() as session:
        order = await crud.get_order(session, callback_data.order_id)
        user = await crud.get_user(session, order.user_id) if order else None
    if user is None:
        await callback.answer("Клієнта не знайдено", show_alert=True)
        return
    await state.clear()
    await state.update_data(reply_to_telegram_id=user.telegram_id)
    await state.set_state(AdminChatFSM.waiting_message)
    await callback.message.answer(
        f"Напишіть повідомлення для клієнта (@{user.username or user.telegram_id}):", reply_markup=cancel_kb()
    )
    await callback.answer()


@router.message(AdminChatFSM.waiting_message, F.text)
async def reply_finish(message: Message, state: FSMContext, bot: Bot) -> None:
    telegram_id = (await state.get_data()).get("reply_to_telegram_id")
    await state.clear()
    sent = await safe_send(
        bot, telegram_id, tx.CHAT_FROM_MANAGER.format(text=escape(message.text)), chat_reply_kb()
    ) if telegram_id else None
    await message.answer("Надіслано ✅" if sent else "Не вдалося надіслати повідомлення клієнту.", reply_markup=admin_main_kb())