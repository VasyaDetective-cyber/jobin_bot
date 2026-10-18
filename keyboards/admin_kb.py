from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from callbacks import AdmCB, AdminCatalogCB, EditorCB, OrderCB, OrderModerationCB, ProductEditFieldCB, StatsCB
from database.models import Category, Product


def admin_main_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🗂 Каталог послуг", callback_data=AdminCatalogCB(action="list_cat"))
    kb.button(text="📋 Черга публікацій", callback_data=AdmCB(section="queue"))
    kb.button(text="📢 Розсилка", callback_data="admin_broadcast")
    kb.button(text="📊 Статистика", callback_data=StatsCB(period="7d"))
    kb.button(text="📥 Експорт в Excel", callback_data=AdmCB(section="export"))
    kb.button(text="🏷 Промокоди", callback_data=AdmCB(section="promo", action="list"))
    kb.button(text="👥 Менеджери і посилання", callback_data=AdmCB(section="mgr", action="list"))
    kb.button(text="💾 Резервна копія бази", callback_data=AdmCB(section="backup"))
    kb.adjust(1)
    return kb.as_markup()


def order_moderation_kb(order_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Підтвердити", callback_data=OrderModerationCB(action="confirm", order_id=order_id))
    kb.button(text="❌ Відхилити", callback_data=OrderModerationCB(action="reject", order_id=order_id))
    kb.button(text="💬 Написати", callback_data=OrderModerationCB(action="reply", order_id=order_id))
    kb.adjust(1)
    return kb.as_markup()


def admin_categories_kb(categories: list[Category]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for cat in categories:
        kb.button(text=cat.name, callback_data=AdminCatalogCB(action="list_prod", id=cat.id))
    kb.button(text="🔙 В адмін-меню", callback_data=AdminCatalogCB(action="back"))
    kb.adjust(1)
    return kb.as_markup()


def admin_products_kb(products: list[Product], category_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for p in products:
        mark = "🟢" if p.is_active else "🔴"
        kb.button(text=f"{mark} {p.name}", callback_data=AdminCatalogCB(action="view", id=p.id))
    kb.button(text="➕ Додати послугу", callback_data=AdminCatalogCB(action="add", id=category_id))
    kb.button(text="🔙 До категорій", callback_data=AdminCatalogCB(action="list_cat"))
    kb.adjust(1)
    return kb.as_markup()


def admin_product_card_kb(product: Product) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Назва", callback_data=ProductEditFieldCB(field="name", id=product.id))
    kb.button(text="✏️ Опис", callback_data=ProductEditFieldCB(field="description", id=product.id))
    kb.button(text="✏️ Ціна", callback_data=ProductEditFieldCB(field="price", id=product.id))
    kb.button(text="✏️ Бонус", callback_data=ProductEditFieldCB(field="bonus", id=product.id))
    kb.button(text="✏️ Посилання", callback_data=ProductEditFieldCB(field="links", id=product.id))
    promo_text = "🎁 Акція 1+1=3: вимкнути" if product.promo_eligible else "🎁 Акція 1+1=3: увімкнути"
    kb.button(text=promo_text, callback_data=AdminCatalogCB(action="promo", id=product.id))
    toggle_text = "🔴 Вимкнути" if product.is_active else "🟢 Увімкнути"
    kb.button(text=toggle_text, callback_data=AdminCatalogCB(action="toggle", id=product.id))
    kb.button(text="🗑 Видалити", callback_data=AdminCatalogCB(action="delete", id=product.id))
    kb.button(text="🔙 До списку", callback_data=AdminCatalogCB(action="list_prod", id=product.category_id))
    kb.adjust(1)
    return kb.as_markup()


def cancel_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Скасувати", callback_data="admin_cancel")
    return kb.as_markup()


def confirm_broadcast_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Надіслати всім", callback_data="broadcast_send")
    kb.button(text="❌ Скасувати", callback_data="broadcast_cancel")
    kb.adjust(1)
    return kb.as_markup()


def reply_only_kb(order_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💬 Написати клієнту", callback_data=OrderModerationCB(action="reply", order_id=order_id))
    return kb.as_markup()


def time_issue_kb(order_id: int) -> InlineKeyboardMarkup:
    """Для менеджера: час потрібно узгодити з клієнтом."""
    kb = InlineKeyboardBuilder()
    kb.button(text="💬 Написати клієнту", callback_data=OrderModerationCB(action="reply", order_id=order_id))
    kb.button(text="🕒 Встановити / змінити час", callback_data=OrderCB(action="admtime", order_id=order_id))
    kb.adjust(1)
    return kb.as_markup()


def editor_kb(order_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Опубліковано", callback_data=EditorCB(action="published", order_id=order_id))
    kb.button(text="⏰ Час зайнятий", callback_data=EditorCB(action="busy", order_id=order_id))
    kb.adjust(1)
    return kb.as_markup()


def editor_skip_kb(order_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Пропустити (без посилання)", callback_data=EditorCB(action="skip", order_id=order_id))
    return kb.as_markup()