from __future__ import annotations

from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
import texts_extra as tx
from callbacks import NavCB, OrderCB, ReviewCB
from database import crud
from database.models import async_session
from handlers import views
from helpers import client_label, safe_send
from keyboards.admin_kb import reply_only_kb
from keyboards.user_kb import back_to_main_kb
from states import ReviewFSM
from utils import fmt

router = Router(name="reviews")
MOODS = {3: "😍 все чудово", 2: "🙂 нормально", 1: "😕 є питання"}


def _skip_kb(order_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="Пропустити", callback_data=ReviewCB(order_id=order_id, rating=0))
    return kb.as_markup()


@router.callback_query(ReviewCB.filter(F.rating > 0))
async def review_rate(callback: CallbackQuery, callback_data: ReviewCB, state: FSMContext, bot: Bot) -> None:
    async with async_session() as session:
        order = await crud.get_order(session, callback_data.order_id)
        user = await crud.get_user(session, order.user_id) if order else None
        if order is None or user is None or user.telegram_id != callback.from_user.id or order.status != "published":
            await callback.answer("Недоступно", show_alert=True)
            return
        if order.review_rating is not None:
            await callback.answer("Дякуємо, ваша оцінка вже є 🙂", show_alert=True)
            return
        order.review_rating = callback_data.rating
        await session.commit()

    rating = callback_data.rating
    kb = InlineKeyboardBuilder()
    if rating == 3:
        text = tx.REVIEW_GOOD.format(percent=fmt(config.REFERRAL_PERCENT))
        kb.button(text="🎁 Запросити друга", callback_data=NavCB(target="referral"))
        kb.button(text="🔁 Повторити замовлення", callback_data=OrderCB(action="repeat", order_id=order.id))
    elif rating == 2:
        text = tx.REVIEW_OK
    else:
        text = tx.REVIEW_BAD
    kb.button(text="🏠 Меню", callback_data=NavCB(target="main_menu"))
    kb.adjust(1)
    await views.reply_or_edit(callback, text, kb.as_markup())
    await callback.answer()

    if rating <= 2:
        for admin_id in config.ADMIN_IDS:
            await safe_send(
                bot, admin_id,
                f"⭐ <b>Відгук до замовлення №{order.id}</b>: {MOODS[rating]}\n👤 {client_label(user)}",
                reply_only_kb(order.id),
            )
    await state.clear()
    await state.set_state(ReviewFSM.waiting_comment)
    await state.update_data(order_id=order.id, rating=rating)
    await callback.message.answer(tx.REVIEW_COMMENT_PROMPT, reply_markup=_skip_kb(order.id))


@router.callback_query(ReviewCB.filter(F.rating == 0))
async def review_skip(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await views.reply_or_edit(callback, tx.REVIEW_COMMENT_THANKS, back_to_main_kb())
    await callback.answer()


@router.message(ReviewFSM.waiting_comment, F.text)
async def review_comment(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    await state.clear()
    text = message.text.strip()[:1500]
    async with async_session() as session:
        order = await crud.get_order(session, data.get("order_id"))
        user = await crud.get_user(session, order.user_id) if order else None
        if order is None or user is None or user.telegram_id != message.from_user.id:
            return
        order.review_comment = text
        await session.commit()
    for admin_id in config.ADMIN_IDS:
        await safe_send(
            bot, admin_id,
            f"⭐ <b>Коментар до замовлення №{order.id}</b> ({MOODS.get(data.get('rating'), '')})\n"
            f"👤 {client_label(user)}\n\n{escape(text)}",
            reply_only_kb(order.id),
        )
    await message.answer(tx.REVIEW_COMMENT_THANKS, reply_markup=back_to_main_kb())