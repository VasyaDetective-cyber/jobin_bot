from __future__ import annotations

from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
import texts_extra as tx
from callbacks import AdmReplyCB, ChatCB
from database import crud
from database.models import async_session
from handlers import views
from helpers import client_label, safe_send
from keyboards.admin_kb import cancel_kb
from keyboards.user_kb import back_to_main_kb
from states import AdminChatFSM, ChatFSM

router = Router(name="support")
ADMIN = F.from_user.id.in_(config.ADMIN_IDS)


@router.callback_query(ChatCB.filter(F.action == "start"))
async def chat_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(ChatFSM.chatting)
    await views.reply_or_edit(callback, tx.CHAT_START, back_to_main_kb())
    await callback.answer()


@router.message(ChatFSM.chatting)
async def chat_message(message: Message, bot: Bot) -> None:
    async with async_session() as session:
        user = await crud.get_or_create_user(
            session, message.from_user.id, message.from_user.username, message.from_user.full_name
        )
        manager = await crud.get_manager(session, user.manager_id)
    header = f"💬 <b>Повідомлення від клієнта</b>\n👤 {client_label(user)}\n🧑‍💼 Менеджер: {escape(manager.name) if manager else '—'}"
    kb = InlineKeyboardBuilder()
    kb.button(text="💬 Відповісти", callback_data=AdmReplyCB(user_id=user.id))
    for admin_id in config.ADMIN_IDS:
        if message.text:
            await safe_send(bot, admin_id, f"{header}\n\n{escape(message.text)}", kb.as_markup())
        else:
            await safe_send(bot, admin_id, header, kb.as_markup())
            try:
                await bot.copy_message(admin_id, message.chat.id, message.message_id)
            except Exception:
                pass
    await message.answer(tx.CHAT_SENT, reply_markup=back_to_main_kb())


@router.callback_query(AdmReplyCB.filter(), ADMIN)
async def admin_reply_start(callback: CallbackQuery, callback_data: AdmReplyCB, state: FSMContext) -> None:
    async with async_session() as session:
        user = await crud.get_user(session, callback_data.user_id)
    if user is None:
        await callback.answer("Клієнта не знайдено", show_alert=True)
        return
    await state.clear()
    await state.update_data(reply_to_telegram_id=user.telegram_id)
    await state.set_state(AdminChatFSM.waiting_message)
    await callback.message.answer(
        f"Напишіть відповідь клієнту (@{user.username or user.telegram_id}):", reply_markup=cancel_kb()
    )
    await callback.answer()
    