from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
from callbacks import BuyCB, CategoryCB, ChatCB, HistCB, NavCB, OrderCB, ProductCB
from database.models import Category, Order, Product


def menu_reply_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🏠 Меню")]], resize_keyboard=True, is_persistent=True
    )


def main_menu_kb(pending: Order | None = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if pending is not None:
        kb.button(text=f"⚡ Продовжити замовлення №{pending.id}", callback_data=OrderCB(action="resume", order_id=pending.id))
    kb.button(text="🛒 Замовити розміщення", callback_data=NavCB(target="catalog"))
    kb.button(text="🗂 Мої замовлення", callback_data=HistCB(page=0))
    kb.button(text=f"🎁 Запросити друга (−{config.REFERRAL_PERCENT:g}%)", callback_data=NavCB(target="referral"))
    kb.button(text="💬 Зв'язок з менеджером", callback_data=NavCB(target="contact_manager"))
    kb.adjust(1)
    return kb.as_markup()


def back_to_main_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🏠 Меню", callback_data=NavCB(target="main_menu"))
    return kb.as_markup()


def categories_kb(categories: list[Category]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for cat in categories:
        kb.button(text=cat.name, callback_data=CategoryCB(id=cat.id))
    kb.button(text="🏠 Меню", callback_data=NavCB(target="main_menu"))
    kb.adjust(1)
    return kb.as_markup()


def products_kb(products: list[Product], category_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for p in products:
        kb.button(text=p.name, callback_data=ProductCB(id=p.id))
    kb.button(text="🔙 Назад", callback_data=NavCB(target="catalog"))
    kb.adjust(1)
    return kb.as_markup()


def product_card_kb(product_id: int, category_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💳 Купити", callback_data=BuyCB(product_id=product_id))
    kb.button(text="🔙 Назад", callback_data=CategoryCB(id=category_id))
    kb.adjust(1)
    return kb.as_markup()


def contact_manager_kb(username: str | None = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✉️ Написати менеджеру", url=f"https://t.me/{username or config.MANAGER_USERNAME}")
    kb.button(text="🏠 Меню", callback_data=NavCB(target="main_menu"))
    kb.adjust(1)
    return kb.as_markup()


def contact_chat_kb(username: str | None = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💬 Написати тут, у боті", callback_data=ChatCB(action="start"))
    kb.button(text="✉️ Написати в Telegram", url=f"https://t.me/{username or config.MANAGER_USERNAME}")
    kb.button(text="🏠 Меню", callback_data=NavCB(target="main_menu"))
    kb.adjust(1)
    return kb.as_markup()


def chat_reply_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💬 Відповісти менеджеру", callback_data=ChatCB(action="start"))
    kb.button(text="🏠 Меню", callback_data=NavCB(target="main_menu"))
    kb.adjust(1)
    return kb.as_markup()


def unsub_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔕 Більше не надсилати", callback_data="unsub")
    return kb.as_markup()


def resub_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔔 Увімкнути розсилки знову", callback_data="resub")
    return kb.as_markup()