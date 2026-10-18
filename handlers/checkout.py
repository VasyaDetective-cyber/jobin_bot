from __future__ import annotations
import asyncio
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
import rates
import texts
import texts_extra as tx
from callbacks import AddonCB, BuyCB, CartCB, NavCB, PromoCB, PromoPickCB
from database import crud
from database.models import Order, Product, User, async_session
from handlers import views
from helpers import order_admin_caption
from keyboards.admin_kb import order_moderation_kb
from keyboards.checkout_kb import addons_kb, promo_gift_kb, promo_offer_kb, promo_paid_kb
from keyboards.user_kb import back_to_main_kb, contact_manager_kb
from states import CartFSM, OrderFSM
from utils import fmt

router = Router(name="checkout")


def _item(p: Product, kind: str = "main") -> dict:
    return {"id": p.id, "name": p.name, "price": float(p.price), "kind": kind}


def _cart_items(cart: dict) -> list[dict]:
    items = [dict(cart["main"], kind="main")]
    if cart.get("paid"):
        items.append(dict(cart["paid"], kind="paid"))
    if cart.get("gift"):
        items.append(dict(cart["gift"], kind="gift"))
    items += [dict(a, kind="addon") for a in cart.get("addons", [])]
    return items


def _subtotal(cart: dict) -> float:
    return sum(i["price"] for i in _cart_items(cart) if i["kind"] != "gift")


def _lines(items: list[dict]) -> list[str]:
    return [
        f"🎁 {i['name']} — у подарунок" if i["kind"] == "gift" else f"{i['name']} — {fmt(i['price'])} грн"
        for i in items
    ]


def _gift_candidates(pool: list[Product], main: dict, paid: dict) -> list[Product]:
    limit = min(main["price"], paid["price"])
    return [p for p in pool if p.id not in (main["id"], paid["id"]) and float(p.price) <= limit]


def _paid_options(pool: list[Product], main: dict) -> list[Product]:
    return [
        b for b in pool
        if b.id != main["id"] and _gift_candidates(pool, main, {"id": b.id, "price": float(b.price)})
    ]


async def _user(event: CallbackQuery | Message) -> User:
    async with async_session() as session:
        return await crud.get_or_create_user(
            session, event.from_user.id, event.from_user.username, event.from_user.full_name
        )


async def _get_cart(state: FSMContext) -> dict | None:
    return (await state.get_data()).get("cart")


async def _expired(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user = await _user(callback)
    _, markup = await views.main_menu_view(user)
    await views.reply_or_edit(callback, texts.SESSION_EXPIRED, markup)
    await callback.answer()


async def build_cart(state: FSMContext, product: Product) -> dict:
    cart = {"main": _item(product), "main_tag": product.tag, "paid": None, "gift": None, "addons": []}
    await state.clear()
    await state.update_data(cart=cart)
    return cart


async def start_cart(target: CallbackQuery, state: FSMContext, product: Product, pool: list[Product]) -> None:
    cart = await build_cart(state, product)
    if product.promo_eligible and _paid_options(pool, cart["main"]):
        await views.reply_or_edit(
            target,
            texts.PROMO_OFFER.format(name=escape(product.name), price=fmt(product.price)),
            promo_offer_kb(),
        )
        await target.answer()
    else:
        await show_addons(target, state)


@router.callback_query(BuyCB.filter())
async def buy(callback: CallbackQuery, callback_data: BuyCB, state: FSMContext) -> None:
    async with async_session() as session:
        product = await crud.get_product(session, callback_data.product_id)
        pool = await crud.get_promo_products(session)
    if product is None or not product.is_active:
        await callback.answer("Послугу не знайдено", show_alert=True)
        return
    await start_cart(callback, state, product, pool)


@router.callback_query(PromoCB.filter())
async def promo_choice(callback: CallbackQuery, callback_data: PromoCB, state: FSMContext) -> None:
    cart = await _get_cart(state)
    if cart is None:
        await _expired(callback, state)
        return
    if callback_data.action == "yes":
        async with async_session() as session:
            pool = await crud.get_promo_products(session)
        options = _paid_options(pool, cart["main"])
        if not options:
            await show_addons(callback, state)
            return
        await views.reply_or_edit(callback, texts.PROMO_PICK_PAID, promo_paid_kb(options))
        await callback.answer()
        return
    if callback_data.action == "no":
        cart["paid"] = cart["gift"] = None
        await state.update_data(cart=cart)
    await show_addons(callback, state)


@router.callback_query(PromoPickCB.filter())
async def promo_pick(callback: CallbackQuery, callback_data: PromoPickCB, state: FSMContext) -> None:
    cart = await _get_cart(state)
    if cart is None:
        await _expired(callback, state)
        return
    async with async_session() as session:
        pool = await crud.get_promo_products(session)
    chosen = {p.id: p for p in pool}.get(callback_data.id)
    main = cart["main"]

    if callback_data.step == "paid":
        if chosen is None or chosen.id not in {p.id for p in _paid_options(pool, main)}:
            await callback.answer("Цей варіант вже недоступний", show_alert=True)
            return
        cart["paid"], cart["gift"] = _item(chosen, "paid"), None
        await state.update_data(cart=cart)
        gifts = _gift_candidates(pool, main, cart["paid"])
        if not gifts:
            await show_addons(callback, state)
            return
        await views.reply_or_edit(callback, texts.PROMO_PICK_GIFT, promo_gift_kb(gifts))
        await callback.answer()
        return

    paid = cart.get("paid")
    if paid is None or chosen is None or chosen.id not in {p.id for p in _gift_candidates(pool, main, paid)}:
        await callback.answer("Цей варіант вже недоступний", show_alert=True)
        return
    cart["gift"] = _item(chosen, "gift")
    await state.update_data(cart=cart)
    await show_addons(callback, state)


async def _available_addons(cart: dict) -> list[Product]:
    async with async_session() as session:
        addons = await crud.get_addons(session)
    if cart.get("main_tag") == "pin_included":
        addons = [a for a in addons if a.tag != "pin"]
    return addons


def _addons_text(addons: list[Product]) -> str:
    blocks = [texts.ADDONS_INTRO]
    blocks += [f"<b>{escape(a.name)} — {fmt(a.price)} грн</b>\n{escape(a.description)}" for a in addons]
    return "\n\n".join(blocks)


async def show_addons(callback: CallbackQuery, state: FSMContext) -> None:
    cart = await _get_cart(state)
    if cart is None:
        await _expired(callback, state)
        return
    addons = await _available_addons(cart)
    if not addons:
        await show_cart(callback, state)
        return
    selected = {a["id"] for a in cart["addons"]}
    await views.reply_or_edit(callback, _addons_text(addons), addons_kb(addons, selected))
    await callback.answer()


@router.callback_query(AddonCB.filter())
async def addon_choice(callback: CallbackQuery, callback_data: AddonCB, state: FSMContext) -> None:
    cart = await _get_cart(state)
    if cart is None:
        await _expired(callback, state)
        return
    if callback_data.action == "done":
        await show_cart(callback, state)
        return
    addons = await _available_addons(cart)
    target = {a.id: a for a in addons}.get(callback_data.id)
    if target is None:
        await callback.answer("Цей варіант вже недоступний", show_alert=True)
        return
    current = [a for a in cart["addons"] if a["id"] != target.id]
    if len(current) == len(cart["addons"]):
        current.append(_item(target, "addon"))
    cart["addons"] = current
    await state.update_data(cart=cart)
    await callback.message.edit_reply_markup(reply_markup=addons_kb(addons, {a["id"] for a in current}))
    await callback.answer()


async def _pricing(user: User, cart: dict) -> dict:
    subtotal = _subtotal(cart)
    percent, source, promo_code, discount_id, note = 0.0, "", None, None, ""
    async with async_session() as session:
        in_cart = cart.get("promo")
        if in_cart:
            promo = await crud.get_promo(session, in_cart["code"])
            if promo and promo.is_active and (promo.max_uses is None or promo.used_count < promo.max_uses):
                percent, source, promo_code = promo.percent, f"promo:{promo.code}", promo.code
        discount = await crud.get_available_discount(session, user.id)
    if discount and discount.percent > percent:
        if promo_code:
            note = tx.PROMO_NOTE_BOTH
        percent, source, promo_code, discount_id = discount.percent, "referral", None, discount.id
    amount = round(subtotal * (1 - percent / 100), 2)
    return {
        "subtotal": subtotal, "percent": percent, "source": source, "promo_code": promo_code,
        "discount_id": discount_id, "amount": amount, "note": note,
    }


async def show_cart(target: CallbackQuery | Message, state: FSMContext) -> None:
    cart = await _get_cart(state)
    if cart is None:
        if isinstance(target, CallbackQuery):
            await _expired(target, state)
        else:
            await state.clear()
            await target.answer(texts.SESSION_EXPIRED, reply_markup=back_to_main_kb())
        return
    user = await _user(target)
    price = await _pricing(user, cart)
    block = "\n".join(f"• {escape(l)}" for l in _lines(_cart_items(cart)))
    if price["percent"]:
        saved = price["subtotal"] - price["amount"]
        label = f"Промокод {cart['promo']['code']}" if price["source"].startswith("promo") else "Знижка за друга"
        block += f"\n\n🏷 {escape(label)}: −{fmt(price['percent'])}% (−{fmt(saved)} грн)"
        if price["note"]:
            block += "\n" + price["note"]
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Оформити замовлення", callback_data=CartCB(action="confirm"))
    if cart.get("promo"):
        kb.button(text="🗑 Прибрати промокод", callback_data=CartCB(action="nocode"))
    else:
        kb.button(text="🏷 Маю промокод", callback_data=CartCB(action="code"))
    kb.button(text="🏠 Меню", callback_data=NavCB(target="main_menu"))
    kb.adjust(1)
    await views.reply_or_edit(target, texts.CART_SUMMARY.format(items=block, total=fmt(price["amount"])), kb.as_markup())
    if isinstance(target, CallbackQuery):
        await target.answer()


@router.callback_query(CartCB.filter(F.action == "code"))
async def cart_code_start(callback: CallbackQuery, state: FSMContext) -> None:
    if await _get_cart(state) is None:
        await _expired(callback, state)
        return
    await state.set_state(CartFSM.waiting_code)
    kb = InlineKeyboardBuilder()
    kb.button(text="↩️ Назад до замовлення", callback_data=CartCB(action="back"))
    await views.reply_or_edit(callback, tx.PROMO_PROMPT, kb.as_markup())
    await callback.answer()


@router.callback_query(CartCB.filter(F.action == "back"))
async def cart_back(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(None)
    await show_cart(callback, state)


@router.callback_query(CartCB.filter(F.action == "nocode"))
async def cart_remove_code(callback: CallbackQuery, state: FSMContext) -> None:
    cart = await _get_cart(state)
    if cart is None:
        await _expired(callback, state)
        return
    cart["promo"] = None
    await state.update_data(cart=cart)
    await show_cart(callback, state)


@router.message(CartFSM.waiting_code, F.text)
async def cart_code_enter(message: Message, state: FSMContext) -> None:
    cart = await _get_cart(state)
    if cart is None:
        await state.clear()
        await message.answer(texts.SESSION_EXPIRED, reply_markup=back_to_main_kb())
        return
    user = await _user(message)
    code = message.text.strip().upper()
    async with async_session() as session:
        promo = await crud.get_promo(session, code)
        used = await crud.user_used_promo(session, user.id, code) if promo else False
    kb = InlineKeyboardBuilder()
    kb.button(text="↩️ Назад до замовлення", callback_data=CartCB(action="back"))
    if promo is None or not promo.is_active or (promo.max_uses is not None and promo.used_count >= promo.max_uses):
        await message.answer(tx.PROMO_INVALID, reply_markup=kb.as_markup())
        return
    if used:
        await message.answer(tx.PROMO_USED, reply_markup=kb.as_markup())
        return
    cart["promo"] = {"code": promo.code, "percent": promo.percent}
    await state.update_data(cart=cart)
    await state.set_state(None)
    await message.answer(tx.PROMO_APPLIED.format(code=escape(promo.code), percent=fmt(promo.percent)))
    await show_cart(message, state)


@router.message(CartFSM.waiting_code)
async def cart_code_not_text(message: Message) -> None:
    kb = InlineKeyboardBuilder()
    kb.button(text="↩️ Назад до замовлення", callback_data=CartCB(action="back"))
    await message.answer(tx.PROMO_NOT_TEXT, reply_markup=kb.as_markup())


_confirm_locks: dict[int, asyncio.Lock] = {}


@router.callback_query(CartCB.filter(F.action == "confirm"))
async def confirm_cart(callback: CallbackQuery, state: FSMContext) -> None:
    lock = _confirm_locks.setdefault(callback.from_user.id, asyncio.Lock())
    async with lock:
        cart = await _get_cart(state)
        if cart is None:
            if await state.get_state() == OrderFSM.waiting_receipt.state:
                await callback.answer()
                return
            await _expired(callback, state)
            return
        user = await _user(callback)
        price = await _pricing(user, cart)
        async with async_session() as session:
            order = await crud.create_order_full(
                session, user.id, _cart_items(cart), price["subtotal"], price["percent"],
                price["source"], price["promo_code"], price["discount_id"],
            )
        await show_payment(callback, state, order)

async def _requisites(total: float) -> tuple[str, str]:
    text = (
        f"💳 Картка: <code>{escape(config.PAYMENT_CARD)}</code>\n"
        f"🏦 IBAN: <code>{escape(config.PAYMENT_IBAN)}</code>"
    )
    note = ""
    if config.PAYMENT_CRYPTO:
        text += f"\n🪙 USDT (TRC-20): <code>{escape(config.PAYMENT_CRYPTO)}</code>"
        rate = await rates.get_usdt_rate()
        if rate:
            usdt = rates.uah_to_usdt(total, rate)
            text += "\n" + texts.CRYPTO_AMOUNT.format(usdt=f"{usdt:.2f}", rate=f"{rate:.2f}")
            text += "\n" + texts.CRYPTO_NOTE
            note = f"≈ {usdt:.2f} USDT (курс {rate:.2f})"
        else:
            text += "\n" + texts.CRYPTO_HINT
    return text, note


async def show_payment(target: CallbackQuery, state: FSMContext, order: Order) -> None:
    requisites, note = await _requisites(order.amount)
    async with async_session() as session:
        await crud.set_pay_note(session, order.id, note)
        user = await crud.get_user(session, order.user_id)
        username = await crud.manager_username_for(session, user)
    await state.clear()
    await state.set_state(OrderFSM.waiting_receipt)
    await state.update_data(order_id=order.id)

    lines = [l for l in (order.items_text or "").splitlines() if l]
    text = texts.PAYMENT.format(
        order_id=order.id,
        items="\n".join(f"• {escape(l)}" for l in lines),
        total=fmt(order.amount),
        requisites=requisites,
    )
    await views.reply_or_edit(target, text, contact_manager_kb(username))
    await target.answer()


@router.message(OrderFSM.waiting_receipt, F.photo | F.document)
async def receive_receipt(message: Message, state: FSMContext, bot: Bot) -> None:
    order_id = (await state.get_data()).get("order_id")
    file_id = message.photo[-1].file_id if message.photo else message.document.file_id

    async with async_session() as session:
        order = await crud.get_order(session, order_id) if order_id else None
        if order is None or order.status != "pending_payment":
            await state.clear()
            await message.answer(
                "Квитанцію до цього замовлення вже отримано 🙌" if order else texts.RECEIPT_NO_ORDER,
                reply_markup=back_to_main_kb(),
            )
            return
        await crud.attach_receipt(session, order.id, file_id)
        order = await crud.get_order(session, order.id)
        user = await crud.get_user(session, order.user_id)
        manager = await crud.get_manager(session, user.manager_id)
        await crud.resolve_user_cart_views(session, user.id)

    await state.clear()
    await message.answer(texts.RECEIPT_THANKS, reply_markup=back_to_main_kb())

    caption = order_admin_caption(order, user, manager.name if manager else None)
    for admin_id in config.ADMIN_IDS:
        try:
            if message.photo:
                sent = await bot.send_photo(admin_id, file_id, caption=caption, reply_markup=order_moderation_kb(order.id))
            else:
                sent = await bot.send_document(admin_id, file_id, caption=caption, reply_markup=order_moderation_kb(order.id))
        except Exception:
            continue
        async with async_session() as session:
            await crud.save_notification(session, order.id, admin_id, sent.message_id, caption)


@router.message(OrderFSM.waiting_receipt)
async def receipt_wrong_type(message: Message, state: FSMContext) -> None:
    order_id = (await state.get_data()).get("order_id")
    async with async_session() as session:
        order = await crud.get_order(session, order_id) if order_id else None
        user = await crud.get_user(session, order.user_id) if order else None
        username = await crud.manager_username_for(session, user)
    await message.answer(texts.RECEIPT_WRONG, reply_markup=contact_manager_kb(username))