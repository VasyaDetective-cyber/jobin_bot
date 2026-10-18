"""Команди та кнопка «🏠 Меню» — працюють з будь-якого стану, тому цей роутер підключається першим."""
from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

import config
import texts
from database import crud
from database.models import User, async_session
from handlers import views
from keyboards.admin_kb import admin_main_kb
from keyboards.user_kb import menu_reply_kb

router = Router(name="common")


async def _user(message: Message) -> User:
    async with async_session() as session:
        return await crud.get_or_create_user(
            session, message.from_user.id, message.from_user.username, message.from_user.full_name
        )


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, state: FSMContext) -> None:
    await state.clear()
    payload = (command.args or "").strip()
    manager_code = payload[2:] if payload.startswith("m_") else None
    referrer_tg = int(payload[4:]) if payload.startswith("ref_") and payload[4:].isdigit() and len(payload[4:]) <= 15 else None

    async with async_session() as session:
        user, created = await crud.register_user(
            session,
            message.from_user.id,
            message.from_user.username,
            message.from_user.full_name,
            manager_code=manager_code,
            referrer_tg=referrer_tg,
        )
    if created:
        greeting = texts.WELCOME_NEW
    else:
        greeting = texts.WELCOME_BACK.format(name=escape(message.from_user.first_name or "друже"))
    await message.answer(greeting, reply_markup=menu_reply_kb())
    text, markup = await views.main_menu_view(user)
    await message.answer(text, reply_markup=markup)


@router.message(Command("menu"))
@router.message(F.text == "🏠 Меню")
async def cmd_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = await _user(message)
    text, markup = await views.main_menu_view(user)
    await message.answer(text, reply_markup=markup)


@router.message(Command("orders"))
async def cmd_orders(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = await _user(message)
    text, markup = await views.history_view(user, 0)
    await message.answer(text, reply_markup=markup)


@router.message(Command("manager"))
async def cmd_manager(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = await _user(message)
    text, markup = await views.contact_view(user)
    await message.answer(text, reply_markup=markup)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    if message.from_user.id in config.ADMIN_IDS:
        await message.answer("Дію скасовано. 🛠 Адмін-панель:", reply_markup=admin_main_kb())
        return
    user = await _user(message)
    text, markup = await views.main_menu_view(user, "Дію скасовано 👌")
    await message.answer(text, reply_markup=markup)