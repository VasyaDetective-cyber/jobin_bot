from __future__ import annotations

import asyncio

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
from callbacks import AdmCB, BcCB
from database import crud, queries
from database.models import async_session
from handlers import views
from keyboards.admin_kb import admin_main_kb, cancel_kb
from keyboards.user_kb import unsub_kb
from states import BroadcastFSM

router = Router(name="admin_crm")
router.message.filter(F.from_user.id.in_(config.ADMIN_IDS))
router.callback_query.filter(F.from_user.id.in_(config.ADMIN_IDS))

SEGMENT_ORDER = ("all", "buyers", "nonbuyers", "inactive7")


async def _count(seg: str, manager_id: int | None = None) -> int:
    async with async_session() as session:
        return len(await queries.segment_users(session, seg, manager_id))


def _controls(count: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="🧪 Надіслати тест собі", callback_data=BcCB(action="test"))
    kb.button(text=f"✅ Надіслати ({count})", callback_data=BcCB(action="send"))
    kb.button(text="❌ Скасувати", callback_data=BcCB(action="cancel"))
    kb.adjust(1)
    return kb.as_markup()


@router.callback_query(F.data == "admin_broadcast")
async def broadcast_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    kb = InlineKeyboardBuilder()
    for seg in SEGMENT_ORDER:
        kb.button(text=f"{queries.SEGMENTS[seg]} ({await _count(seg)})", callback_data=BcCB(action="seg", seg=seg))
    kb.button(text="🧑‍💼 За менеджером", callback_data=BcCB(action="mgrs"))
    kb.button(text="🔙 Адмін-меню", callback_data=AdmCB(section="home"))
    kb.adjust(1)
    await views.reply_or_edit(callback, "📢 <b>Кому надіслати розсилку?</b>\nУ дужках — скільки отримувачів.", kb.as_markup())
    await callback.answer()


@router.callback_query(BcCB.filter(F.action == "mgrs"))
async def broadcast_managers(callback: CallbackQuery) -> None:
    async with async_session() as session:
        managers = await crud.get_managers(session)
    kb = InlineKeyboardBuilder()
    for m in managers:
        kb.button(text=f"{m.name} ({await _count('manager', m.id)})", callback_data=BcCB(action="seg", seg="manager", id=m.id))
    kb.button(text="🔙 Назад", callback_data="admin_broadcast")
    kb.adjust(1)
    await views.reply_or_edit(callback, "🧑‍💼 Клієнтам якого менеджера надіслати?", kb.as_markup())
    await callback.answer()


@router.callback_query(BcCB.filter(F.action == "seg"))
async def broadcast_segment(callback: CallbackQuery, callback_data: BcCB, state: FSMContext) -> None:
    count = await _count(callback_data.seg, callback_data.id or None)
    await state.clear()
    await state.update_data(seg=callback_data.seg, manager_id=callback_data.id or None)
    await state.set_state(BroadcastFSM.waiting_content)
    await callback.message.answer(
        f"📢 Група: <b>{queries.SEGMENTS[callback_data.seg]}</b> (отримувачів: {count}).\n\n"
        "Надішліть повідомлення для розсилки — текст, фото, відео чи файл:",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(BroadcastFSM.waiting_content)
async def broadcast_preview(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    count = await _count(data["seg"], data.get("manager_id"))
    await state.update_data(src_chat=message.chat.id, src_msg=message.message_id)
    await state.set_state(BroadcastFSM.waiting_confirm)
    await message.answer("👇 Так повідомлення побачать клієнти:")
    await bot.copy_message(message.chat.id, message.chat.id, message.message_id, reply_markup=unsub_kb())
    await message.answer(f"Надіслати групі «{queries.SEGMENTS[data['seg']]}»?", reply_markup=_controls(count))


@router.callback_query(BcCB.filter(F.action == "cancel"))
async def broadcast_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await views.reply_or_edit(callback, "Розсилку скасовано.", admin_main_kb())
    await callback.answer()


@router.callback_query(BcCB.filter(F.action == "test"), BroadcastFSM.waiting_confirm)
async def broadcast_test(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    await bot.copy_message(callback.from_user.id, data["src_chat"], data["src_msg"], reply_markup=unsub_kb())
    await callback.answer("Тест надіслано вам у чат")


@router.callback_query(BcCB.filter(F.action == "send"), BroadcastFSM.waiting_confirm)
async def broadcast_send(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    await state.clear()
    async with async_session() as session:
        users = await queries.segment_users(session, data["seg"], data.get("manager_id"))
    await callback.answer()
    await callback.message.answer(f"📤 Починаю розсилку на {len(users)} клієнтів...")

    sent = failed = blocked = 0
    for user in users:
        for _ in range(2):
            try:
                await bot.copy_message(user.telegram_id, data["src_chat"], data["src_msg"], reply_markup=unsub_kb())
                sent += 1
                break
            except TelegramRetryAfter as exc:
                await asyncio.sleep(exc.retry_after + 1)
            except TelegramForbiddenError:
                blocked += 1
                async with async_session() as session:
                    await crud.mark_blocked(session, user.telegram_id)
                break
            except (TelegramBadRequest, Exception):
                failed += 1
                break
        await asyncio.sleep(0.05)

    await callback.message.answer(
        f"✅ Розсилку завершено.\nДоставлено: {sent}\nЗаблокували бота: {blocked}\nПомилок: {failed}",
        reply_markup=admin_main_kb(),
    )