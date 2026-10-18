from __future__ import annotations

from urllib.parse import quote

from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select

import app_state
import config
import texts_extra as tx
from callbacks import NavCB
from database import crud
from database.models import Discount, User, async_session
from handlers import views
from keyboards.user_kb import resub_kb
from utils import fmt

router = Router(name="referral")


@router.callback_query(NavCB.filter(F.target == "referral"))
async def referral_screen(callback: CallbackQuery) -> None:
    async with async_session() as session:
        user = await crud.get_or_create_user(
            session, callback.from_user.id, callback.from_user.username, callback.from_user.full_name
        )
        invited = (await session.execute(select(func.count(User.id)).where(User.referred_by == user.id))).scalar_one()
        bought = (
            await session.execute(
                select(func.count(Discount.id)).where(Discount.user_id == user.id, Discount.friend_user_id.is_not(None))
            )
        ).scalar_one()
        free = await crud.count_free_discounts(session, user.id)

    link = f"https://t.me/{app_state.bot_username}?start=ref_{user.telegram_id}"
    text = tx.REFERRAL_INFO.format(
        percent=fmt(config.REFERRAL_PERCENT), link=link, invited=invited, bought=bought, free=free
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="📤 Поділитися з другом", url=f"https://t.me/share/url?url={quote(link)}&text={quote(tx.REFERRAL_SHARE)}")
    kb.button(text="🏠 Меню", callback_data=NavCB(target="main_menu"))
    kb.adjust(1)
    await views.reply_or_edit(callback, text, kb.as_markup())
    await callback.answer()


@router.callback_query(F.data == "unsub")
async def unsubscribe(callback: CallbackQuery) -> None:
    async with async_session() as session:
        await crud.set_unsubscribed(session, callback.from_user.id, True)
    await callback.message.answer(tx.UNSUB_DONE, reply_markup=resub_kb())
    await callback.answer()


@router.callback_query(F.data == "resub")
async def resubscribe(callback: CallbackQuery) -> None:
    async with async_session() as session:
        await crud.set_unsubscribed(session, callback.from_user.id, False)
    await callback.message.edit_text(tx.RESUB_DONE)
    await callback.answer()