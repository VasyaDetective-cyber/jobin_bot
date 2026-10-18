from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from callbacks import AddonCB, NavCB, PromoCB, PromoPickCB
from database.models import Product
from utils import fmt


def promo_offer_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🎁 Так, хочу акцію", callback_data=PromoCB(action="yes"))
    kb.button(text="Ні, дякую — без акції", callback_data=PromoCB(action="no"))
    kb.adjust(1)
    return kb.as_markup()


def promo_paid_kb(options: list[Product]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for p in options:
        kb.button(text=f"{p.name} — {fmt(p.price)} грн", callback_data=PromoPickCB(step="paid", id=p.id))
    kb.button(text="↩️ Без акції", callback_data=PromoCB(action="no"))
    kb.adjust(1)
    return kb.as_markup()


def promo_gift_kb(options: list[Product]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for p in options:
        kb.button(
            text=f"🎁 {p.name} (замість {fmt(p.price)} грн)",
            callback_data=PromoPickCB(step="gift", id=p.id),
        )
    kb.button(text="Без подарунка", callback_data=PromoCB(action="nogift"))
    kb.adjust(1)
    return kb.as_markup()


def addons_kb(addons: list[Product], selected_ids: set[int]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    extra = 0.0
    for a in addons:
        chosen = a.id in selected_ids
        if chosen:
            extra += float(a.price)
        mark = "✅" if chosen else "➕"
        kb.button(text=f"{mark} {a.name} — {fmt(a.price)} грн", callback_data=AddonCB(action="toggle", id=a.id))
    if selected_ids:
        kb.button(text=f"Далі ➡️ (+{fmt(extra)} грн)", callback_data=AddonCB(action="done"))
    else:
        kb.button(text="Далі, без доповнень ➡️", callback_data=AddonCB(action="done"))
    kb.button(text="🔙 В меню", callback_data=NavCB(target="main_menu"))
    kb.adjust(1)
    return kb.as_markup()
