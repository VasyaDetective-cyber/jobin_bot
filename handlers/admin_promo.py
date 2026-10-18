from __future__ import annotations

import re
from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
from callbacks import AdmCB
from database import crud
from database.models import async_session
from handlers import views
from keyboards.admin_kb import cancel_kb
from states import AdminPromoFSM
from utils import fmt

router = Router(name="admin_promo")
router.message.filter(F.from_user.id.in_(config.ADMIN_IDS))
router.callback_query.filter(F.from_user.id.in_(config.ADMIN_IDS))


def _line(p) -> str:
    limit = p.max_uses if p.max_uses is not None else "∞"
    mark = "🟢" if p.is_active else "🔴"
    return f"{mark} <code>{escape(p.code)}</code> · −{fmt(p.percent)}% · використано {p.used_count}/{limit}"


@router.callback_query(AdmCB.filter((F.section == "promo") & (F.action == "list")))
async def promo_list(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    async with async_session() as session:
        promos = await crud.list_promos(session)
    lines = ["🏷 <b>Промокоди</b>", ""] + ([_line(p) for p in promos] or ["Поки немає жодного промокоду."])
    kb = InlineKeyboardBuilder()
    for p in promos:
        kb.button(text=f"✏️ {p.code}", callback_data=AdmCB(section="promo", action="view", id=p.id))
    kb.button(text="➕ Створити промокод", callback_data=AdmCB(section="promo", action="add"))
    kb.button(text="🔙 Адмін-меню", callback_data=AdmCB(section="home"))
    kb.adjust(1)
    await views.reply_or_edit(callback, "\n".join(lines), kb.as_markup())
    await callback.answer()


async def _card(target, promo_id: int) -> None:
    async with async_session() as session:
        promos = await crud.list_promos(session)
    promo = next((p for p in promos if p.id == promo_id), None)
    if promo is None:
        await views.reply_or_edit(target, "Промокод не знайдено.", None)
        return
    kb = InlineKeyboardBuilder()
    kb.button(
        text="🔴 Вимкнути" if promo.is_active else "🟢 Увімкнути",
        callback_data=AdmCB(section="promo", action="toggle", id=promo.id),
    )
    kb.button(text="🗑 Видалити", callback_data=AdmCB(section="promo", action="delete", id=promo.id))
    kb.button(text="🔙 До списку", callback_data=AdmCB(section="promo", action="list"))
    kb.adjust(1)
    await views.reply_or_edit(target, _line(promo), kb.as_markup())


@router.callback_query(AdmCB.filter((F.section == "promo") & (F.action == "view")))
async def promo_view(callback: CallbackQuery, callback_data: AdmCB) -> None:
    await _card(callback, callback_data.id)
    await callback.answer()


@router.callback_query(AdmCB.filter((F.section == "promo") & (F.action == "toggle")))
async def promo_toggle(callback: CallbackQuery, callback_data: AdmCB) -> None:
    async with async_session() as session:
        await crud.toggle_promo_active(session, callback_data.id)
    await _card(callback, callback_data.id)
    await callback.answer("Змінено")


@router.callback_query(AdmCB.filter((F.section == "promo") & (F.action == "delete")))
async def promo_delete(callback: CallbackQuery, callback_data: AdmCB, state: FSMContext) -> None:
    async with async_session() as session:
        await crud.delete_promo(session, callback_data.id)
    await promo_list(callback, state)


@router.callback_query(AdmCB.filter((F.section == "promo") & (F.action == "add")))
async def promo_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AdminPromoFSM.code)
    await callback.message.answer(
        "Введіть промокод (латиницею/цифрами, 3–32 символи), наприклад SALE10:", reply_markup=cancel_kb()
    )
    await callback.answer()


@router.message(AdminPromoFSM.code, F.text)
async def promo_add_code(message: Message, state: FSMContext) -> None:
    code = message.text.strip().upper()
    if not re.fullmatch(r"[A-Z0-9_-]{3,32}", code):
        await message.answer("Лише латиниця, цифри, - та _ (3–32 символи). Спробуйте ще раз:", reply_markup=cancel_kb())
        return
    async with async_session() as session:
        exists = await crud.get_promo(session, code)
    if exists is not None:
        await message.answer("Такий промокод уже є. Введіть інший:", reply_markup=cancel_kb())
        return
    await state.update_data(code=code)
    await state.set_state(AdminPromoFSM.percent)
    await message.answer("Розмір знижки у відсотках (1–90):", reply_markup=cancel_kb())


@router.message(AdminPromoFSM.percent, F.text)
async def promo_add_percent(message: Message, state: FSMContext) -> None:
    try:
        percent = float(message.text.strip().replace(",", "."))
    except ValueError:
        percent = 0
    if not 1 <= percent <= 90:
        await message.answer("Введіть число від 1 до 90:", reply_markup=cancel_kb())
        return
    await state.update_data(percent=percent)
    await state.set_state(AdminPromoFSM.max_uses)
    await message.answer("Скільки разів можна використати? Число або 0 — без обмежень:", reply_markup=cancel_kb())


@router.message(AdminPromoFSM.max_uses, F.text)
async def promo_add_max(message: Message, state: FSMContext) -> None:
    raw = message.text.strip()
    if not raw.isdigit():
        await message.answer("Введіть ціле число (0 — без обмежень):", reply_markup=cancel_kb())
        return
    data = await state.get_data()
    await state.clear()
    async with async_session() as session:
        promo = await crud.create_promo(session, data["code"], data["percent"], int(raw) or None)
    await _card(message, promo.id)