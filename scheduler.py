from __future__ import annotations

import datetime as dt
import logging
import os
from html import escape

from aiogram import Bot
from aiogram.types import FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

import backup
import config
import texts
import texts_extra as tx
from callbacks import NavCB, ReviewCB
from database import crud
from database.models import Order, async_session
from helpers import safe_send
from timeutil import in_message_window, utcnow

log = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone=config.TIMEZONE)


async def job_abandoned(bot: Bot) -> None:
    if not in_message_window():
        return
    now = utcnow()
    cutoff = now - dt.timedelta(hours=config.ABANDONED_DELAY_HOURS)
    async with async_session() as session:
        due = await crud.get_due_cart_views(session, cutoff)
        by_user: dict[int, list] = {}
        for view in due:
            by_user.setdefault(view.user_id, []).append(view)

        for user_id, views_ in by_user.items():
            user = await crud.get_user(session, user_id)
            newest = max(views_, key=lambda v: v.viewed_at)
            stale = newest.viewed_at < now - dt.timedelta(hours=72)
            if not stale and await crud.recently_reminded(session, user_id, now - dt.timedelta(hours=24)):
                continue
            if user is not None and not user.blocked and not stale:
                product = await crud.get_product(session, newest.product_id)
                username = await crud.manager_username_for(session, user)
                kb = InlineKeyboardBuilder()
                kb.button(text="✉️ Написати менеджеру", url=f"https://t.me/{username}")
                kb.button(text="🛒 Обрати розміщення", callback_data=NavCB(target="catalog"))
                kb.button(text="🏠 Меню", callback_data=NavCB(target="main_menu"))
                kb.adjust(1)
                name = product.name if product else "розміщення"
                await safe_send(bot, user.telegram_id, texts.ABANDONED.format(name=escape(name)), kb.as_markup())
            for view in views_:
                view.reminded = True
                view.reminded_at = now
            await session.commit()


async def job_reviews(bot: Bot) -> None:
    if not in_message_window():
        return
    now = utcnow()
    cutoff = now - dt.timedelta(days=config.REVIEW_DELAY_DAYS)
    stale = now - dt.timedelta(days=14)
    async with async_session() as session:
        orders = (
            await session.execute(
                select(Order).where(
                    Order.status == "published", Order.review_requested.is_(False), Order.published_at <= cutoff
                )
            )
        ).scalars().all()
        for order in orders:
            user = await crud.get_user(session, order.user_id)
            if user is not None and not user.blocked and order.published_at >= stale:
                kb = InlineKeyboardBuilder()
                kb.button(text="😍 Все чудово", callback_data=ReviewCB(order_id=order.id, rating=3))
                kb.button(text="🙂 Нормально", callback_data=ReviewCB(order_id=order.id, rating=2))
                kb.button(text="😕 Є питання", callback_data=ReviewCB(order_id=order.id, rating=1))
                kb.adjust(1)
                await safe_send(bot, user.telegram_id, tx.REVIEW_REQUEST.format(order_id=order.id), kb.as_markup())
            order.review_requested = True
        await session.commit()


async def job_backup(bot: Bot) -> None:
    if not config.ADMIN_IDS:
        return
    path, name = await backup.create_backup()
    try:
        await bot.send_document(
            config.ADMIN_IDS[0], FSInputFile(path, filename=name), caption="💾 Щоденна резервна копія бази JOBIN"
        )
    except Exception:
        log.exception("Не вдалося надіслати резервну копію")
    finally:
        os.remove(path)


def setup_jobs(bot: Bot) -> None:
    scheduler.add_job(job_abandoned, "interval", minutes=5, args=[bot], id="abandoned",
                      replace_existing=True, max_instances=1, coalesce=True)
    scheduler.add_job(job_reviews, "interval", minutes=30, args=[bot], id="reviews",
                      replace_existing=True, max_instances=1, coalesce=True)
    scheduler.add_job(job_backup, "cron", hour=config.BACKUP_HOUR, minute=0, args=[bot], id="backup",
                      replace_existing=True, max_instances=1, coalesce=True)