"""Типізовані callback_data фабрики (aiogram 3.x). Розмір callback_data не більше 64 байтів."""
from aiogram.filters.callback_data import CallbackData


# ---------- клієнт: меню і каталог ----------
class NavCB(CallbackData, prefix="nav"):
    target: str  # main_menu | catalog | contact_manager | referral


class CategoryCB(CallbackData, prefix="cat"):
    id: int


class ProductCB(CallbackData, prefix="prod"):
    id: int


class BuyCB(CallbackData, prefix="buy"):
    product_id: int


# ---------- клієнт: акція 1+1=3, доповнення, кошик ----------
class PromoCB(CallbackData, prefix="promo"):
    action: str  # yes (хочу акцію) | no (без акції) | nogift (без подарунка)


class PromoPickCB(CallbackData, prefix="ppick"):
    step: str  # paid | gift
    id: int


class AddonCB(CallbackData, prefix="addon"):
    action: str  # toggle | done
    id: int = 0


class CartCB(CallbackData, prefix="cart"):
    action: str  # confirm | code | nocode | back


# ---------- клієнт: замовлення ----------
class HistCB(CallbackData, prefix="hist"):
    page: int = 0


class OrderCB(CallbackData, prefix="ord"):
    # клієнт: resume | pay | vacancy | schedule | repeat | discuss
    # персонал: card | admtime
    action: str
    order_id: int


class VacancyCB(CallbackData, prefix="vac"):
    action: str  # ok | edit
    order_id: int


class DatePageCB(CallbackData, prefix="dpg"):
    order_id: int
    page: int


class DateCB(CallbackData, prefix="dt"):
    order_id: int
    d: str  # YYYYMMDD


class SlotCB(CallbackData, prefix="slot"):
    order_id: int
    d: str  # YYYYMMDD
    h: int


class ReviewCB(CallbackData, prefix="rev"):
    order_id: int
    rating: int  # 1..3, 0 — пропустити коментар


class ChatCB(CallbackData, prefix="chat"):
    action: str  # start


# ---------- редактор ----------
class EditorCB(CallbackData, prefix="edt"):
    action: str  # published | busy | skip
    order_id: int


# ---------- адмін ----------
class OrderModerationCB(CallbackData, prefix="ordmod"):
    action: str  # confirm | reject | reply
    order_id: int


class AdmReplyCB(CallbackData, prefix="areply"):
    user_id: int  # id клієнта в БД


class AdminCatalogCB(CallbackData, prefix="admcat"):
    action: str  # list_cat | list_prod | view | add | toggle | promo | delete | back
    id: int = 0


class ProductEditFieldCB(CallbackData, prefix="pedit"):
    field: str  # name | description | price | bonus | links
    id: int


class AdmCB(CallbackData, prefix="adm"):
    section: str  # home | queue | export | backup | promo | mgr
    action: str = ""
    id: int = 0


class StatsCB(CallbackData, prefix="st"):
    period: str  # today | 7d | 30d | all


class BcCB(CallbackData, prefix="bc"):
    action: str  # start | seg | mgrs | test | send | cancel
    seg: str = ""
    id: int = 0