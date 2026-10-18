"""Меню, каталог, картка послуги, зв'язок з менеджером та «страховка» для випадкових повідомлень."""
from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import texts
from callbacks import CategoryCB, HistCB, NavCB, ProductCB
from database import crud
from database.models import User, async_session
from handlers import views
from keyboards.user_kb import categories_kb, main_menu_kb, product_card_kb, products_kb
from utils import fmt

router = Router(name="user")


async def _user(event: CallbackQuery | Message) -> User:
    async with async_session() as session:
        return await crud.get_or_create_user(
            session, event.from_user.id, event.from_user.username, event.from_user.full_name
        )


@router.callback_query(NavCB.filter(F.target == "main_menu"))
async def nav_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user = await _user(callback)
    text, markup = await views.main_menu_view(user)
    await views.reply_or_edit(callback, text, markup)
    await callback.answer()


@router.callback_query(NavCB.filter(F.target == "catalog"))
async def nav_catalog(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    async with async_session() as session:
        categories = await crud.get_categories(session)
    await views.reply_or_edit(callback, "🗂 Оберіть категорію послуг:", categories_kb(categories))
    await callback.answer()


@router.callback_query(NavCB.filter(F.target == "contact_manager"))
async def nav_contact(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user = await _user(callback)
    text, markup = await views.contact_view(user)
    await views.reply_or_edit(callback, text, markup)
    await callback.answer()


@router.callback_query(HistCB.filter())
async def nav_history(callback: CallbackQuery, callback_data: HistCB, state: FSMContext) -> None:
    await state.clear()
    user = await _user(callback)
    text, markup = await views.history_view(user, callback_data.page)
    await views.reply_or_edit(callback, text, markup)
    await callback.answer()


@router.callback_query(CategoryCB.filter())
async def show_category_products(callback: CallbackQuery, callback_data: CategoryCB) -> None:
    async with async_session() as session:
        category = await crud.get_category(session, callback_data.id)
        products = await crud.get_products_by_category(session, callback_data.id)
        categories = await crud.get_categories(session)
    if category is None:
        await callback.answer("Категорію не знайдено", show_alert=True)
        return
    if not products:
        await views.reply_or_edit(
            callback, f"У категорії «{escape(category.name)}» поки немає активних послуг.", categories_kb(categories)
        )
        await callback.answer()
        return
    await views.reply_or_edit(
        callback, f"📦 <b>{escape(category.name)}</b>\nОберіть послугу:", products_kb(products, callback_data.id)
    )
    await callback.answer()


def format_product_card(product) -> str:
    lines = [f"<b>{escape(product.name)}</b>", "", escape(product.description or "—"), ""]
    lines.append(f"💰 Ціна: <b>{fmt(product.price)} грн</b>")
    if product.bonus:
        lines += ["", escape(product.bonus)]
    if product.links:
        lines += ["", "🔗 Посилання:"]
        lines += [link.strip() for link in product.links.splitlines() if link.strip()]
    return "\n".join(lines)


@router.callback_query(ProductCB.filter())
async def show_product_card(callback: CallbackQuery, callback_data: ProductCB) -> None:
    user = await _user(callback)
    async with async_session() as session:
        product = await crud.get_product(session, callback_data.id)
        if product is None or not product.is_active:
            await callback.answer("Послугу не знайдено", show_alert=True)
            return
        await crud.add_cart_view(session, user.id, product.id)  # для нагадування про покинутий кошик
    await views.reply_or_edit(
        callback, format_product_card(product), product_card_kb(product.id, product.category_id)
    )
    await callback.answer()


# ---------- «страховка»: ніхто не лишається без відповіді ----------

@router.message(F.photo | F.document)
async def stray_file(message: Message) -> None:
    await message.answer(texts.RECEIPT_NO_ORDER, reply_markup=main_menu_kb())


@router.message()
async def stray_message(message: Message) -> None:
    user = await _user(message)
    text, markup = await views.main_menu_view(user, "Не зовсім зрозумів 🙂 Оберіть, будь ласка, дію з меню:")
    await message.answer(text, reply_markup=markup)