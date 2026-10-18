from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config
from callbacks import AdminCatalogCB, ProductEditFieldCB
from database import crud
from database.models import async_session
from utils import fmt
from keyboards.admin_kb import (
    admin_categories_kb,
    admin_main_kb,
    admin_product_card_kb,
    admin_products_kb,
    cancel_kb,
)
from states import AdminCatalogFSM

router = Router(name="admin_catalog")
router.message.filter(F.from_user.id.in_(config.ADMIN_IDS))
router.callback_query.filter(F.from_user.id.in_(config.ADMIN_IDS))

FIELD_LABELS = {
    "name": "назву",
    "description": "опис",
    "price": "ціну (число)",
    "bonus": "текст бонусу",
    "links": "посилання (кожне з нового рядка)",
}


def _format_admin_product_card(product) -> str:
    status = "🟢 активна" if product.is_active else "🔴 вимкнена"
    return (
        f"<b>{product.name}</b> ({status})\n\n"
        f"Опис: {product.description or '—'}\n"
        f"Ціна: {fmt(product.price)} грн\n"
        f"Акція 1+1=3: {'так' if product.promo_eligible else 'ні'}\n"
        f"Бонус: {product.bonus or '—'}\n"
        f"Посилання:\n{product.links or '—'}"
    )


@router.callback_query(AdminCatalogCB.filter(F.action == "back"))
async def back_to_admin_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("🛠 Адмін-панель JOBIN", reply_markup=admin_main_kb())
    await callback.answer()


@router.callback_query(AdminCatalogCB.filter(F.action == "list_cat"))
async def list_categories(callback: CallbackQuery) -> None:
    async with async_session() as session:
        categories = await crud.get_categories(session, include_addons=True)
    await callback.message.edit_text(
        "🗂 Оберіть категорію для керування послугами:", reply_markup=admin_categories_kb(categories)
    )
    await callback.answer()


@router.callback_query(AdminCatalogCB.filter(F.action == "list_prod"))
async def list_products(callback: CallbackQuery, callback_data: AdminCatalogCB) -> None:
    async with async_session() as session:
        category = await crud.get_category(session, callback_data.id)
        products = await crud.get_products_by_category(session, callback_data.id, only_active=False)
    if category is None:
        await callback.answer("Категорію не знайдено", show_alert=True)
        return
    await callback.message.edit_text(
        f"📦 <b>{category.name}</b>", reply_markup=admin_products_kb(products, callback_data.id)
    )
    await callback.answer()


@router.callback_query(AdminCatalogCB.filter(F.action == "view"))
async def view_product(callback: CallbackQuery, callback_data: AdminCatalogCB) -> None:
    async with async_session() as session:
        product = await crud.get_product(session, callback_data.id)
    if product is None:
        await callback.answer("Послугу не знайдено", show_alert=True)
        return
    await callback.message.edit_text(
        _format_admin_product_card(product), reply_markup=admin_product_card_kb(product)
    )
    await callback.answer()


@router.callback_query(AdminCatalogCB.filter(F.action == "toggle"))
async def toggle_product(callback: CallbackQuery, callback_data: AdminCatalogCB) -> None:
    async with async_session() as session:
        await crud.toggle_product_active(session, callback_data.id)
        product = await crud.get_product(session, callback_data.id)
    await callback.message.edit_text(
        _format_admin_product_card(product), reply_markup=admin_product_card_kb(product)
    )
    await callback.answer("Статус змінено")


@router.callback_query(AdminCatalogCB.filter(F.action == "promo"))
async def toggle_promo(callback: CallbackQuery, callback_data: AdminCatalogCB) -> None:
    async with async_session() as session:
        await crud.toggle_product_promo(session, callback_data.id)
        product = await crud.get_product(session, callback_data.id)
    await callback.message.edit_text(
        _format_admin_product_card(product), reply_markup=admin_product_card_kb(product)
    )
    await callback.answer("Змінено")


@router.callback_query(AdminCatalogCB.filter(F.action == "delete"))
async def delete_product(callback: CallbackQuery, callback_data: AdminCatalogCB) -> None:
    async with async_session() as session:
        product = await crud.get_product(session, callback_data.id)
        category_id = product.category_id if product else None
        await crud.delete_product(session, callback_data.id)
        products = await crud.get_products_by_category(session, category_id, only_active=False) if category_id else []
        category = await crud.get_category(session, category_id) if category_id else None

    if category is None:
        await callback.answer("Видалено", show_alert=True)
        return
    await callback.message.edit_text(
        f"📦 <b>{category.name}</b>\n\n🗑 Послугу видалено.",
        reply_markup=admin_products_kb(products, category_id),
    )
    await callback.answer()


@router.callback_query(AdminCatalogCB.filter(F.action == "add"))
async def add_product_start(callback: CallbackQuery, callback_data: AdminCatalogCB, state: FSMContext) -> None:
    await state.update_data(new_product_category_id=callback_data.id)
    await state.set_state(AdminCatalogFSM.waiting_new_product_name)
    await callback.message.answer("Введіть назву нової послуги:", reply_markup=cancel_kb())
    await callback.answer()


@router.message(AdminCatalogFSM.waiting_new_product_name)
async def add_product_finish(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    category_id = data.get("new_product_category_id")
    name = (message.text or "").strip()
    if not name:
        await message.answer("Назва не може бути порожньою. Спробуйте ще раз:")
        return

    async with async_session() as session:
        product = await crud.create_product(session, category_id, name)

    await state.clear()
    await message.answer(
        _format_admin_product_card(product), reply_markup=admin_product_card_kb(product)
    )


@router.callback_query(ProductEditFieldCB.filter())
async def edit_product_field_start(
    callback: CallbackQuery, callback_data: ProductEditFieldCB, state: FSMContext
) -> None:
    await state.update_data(edit_product_id=callback_data.id, edit_field=callback_data.field)
    await state.set_state(AdminCatalogFSM.waiting_field_value)
    label = FIELD_LABELS.get(callback_data.field, callback_data.field)
    await callback.message.answer(
        f"Введіть нове значення для поля «{label}»:", reply_markup=cancel_kb()
    )
    await callback.answer()


@router.message(AdminCatalogFSM.waiting_field_value)
async def edit_product_field_finish(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    product_id = data.get("edit_product_id")
    field = data.get("edit_field")
    raw_value = message.text or ""

    if field == "price":
        try:
            value = float(raw_value.replace(",", ".").strip())
        except ValueError:
            await message.answer("Ціна має бути числом. Спробуйте ще раз:")
            return
    else:
        value = raw_value

    async with async_session() as session:
        await crud.update_product_field(session, product_id, field, value)
        product = await crud.get_product(session, product_id)

    await state.clear()
    await message.answer(
        _format_admin_product_card(product), reply_markup=admin_product_card_kb(product)
    )
