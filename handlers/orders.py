from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

import texts
from callbacks import OrderCB
from database import crud
from database.models import Order, User, async_session
from handlers import checkout, views
from handlers.vacancy import notify_time_issue, prompt_vacancy, show_dates
from keyboards.user_kb import back_to_main_kb

router = Router(name="orders")


async def _own(callback: CallbackQuery, order_id: int) -> tuple[User, Order] | None:
    async with async_session() as session:
        user = await crud.get_or_create_user(
            session, callback.from_user.id, callback.from_user.username, callback.from_user.full_name
        )
        order = await crud.get_order(session, order_id)
    if order is None or order.user_id != user.id:
        await callback.answer("Замовлення не знайдено", show_alert=True)
        return None
    return user, order


async def _show_history(callback: CallbackQuery, user: User) -> None:
    text, markup = await views.history_view(user, 0)
    await views.reply_or_edit(callback, text, markup)
    await callback.answer()


async def _route(callback: CallbackQuery, state: FSMContext, user: User, order: Order) -> None:
    if order.status == "pending_payment":
        await checkout.show_payment(callback, state, order)
    elif order.status == "confirmed" or (order.status == "awaiting_time" and not order.vacancy_text):
        await prompt_vacancy(callback, state, order)
    elif order.status == "awaiting_time":
        await show_dates(callback, order.id)
    else:
        await _show_history(callback, user)


@router.callback_query(OrderCB.filter(F.action.in_({"resume", "pay"})))
async def resume_order(callback: CallbackQuery, callback_data: OrderCB, state: FSMContext) -> None:
    found = await _own(callback, callback_data.order_id)
    if found:
        await _route(callback, state, *found)


@router.callback_query(OrderCB.filter(F.action == "vacancy"))
async def order_vacancy(callback: CallbackQuery, callback_data: OrderCB, state: FSMContext) -> None:
    found = await _own(callback, callback_data.order_id)
    if not found:
        return
    user, order = found
    if order.status in ("confirmed", "awaiting_time"):
        await prompt_vacancy(callback, state, order)
    else:
        await _show_history(callback, user)


@router.callback_query(OrderCB.filter(F.action == "schedule"))
async def order_schedule(callback: CallbackQuery, callback_data: OrderCB, state: FSMContext) -> None:
    found = await _own(callback, callback_data.order_id)
    if not found:
        return
    user, order = found
    if order.status == "awaiting_time" and order.vacancy_text:
        await show_dates(callback, order.id)
    else:
        await _route(callback, state, user, order)


@router.callback_query(OrderCB.filter(F.action == "discuss"))
async def order_discuss(callback: CallbackQuery, callback_data: OrderCB, bot: Bot) -> None:
    found = await _own(callback, callback_data.order_id)
    if not found:
        return
    user, order = found
    if order.status != "awaiting_time":
        await callback.answer("Це замовлення вже заплановано", show_alert=True)
        return
    async with async_session() as session:
        await crud.set_time_note(session, order.id, "discuss")
    await notify_time_issue(bot, order, user, "🤝 Клієнт хоче <b>обговорити час публікації</b>. Зв'яжіться з ним і встановіть час кнопкою нижче.")
    await views.reply_or_edit(callback, texts.DISCUSS_TIME, back_to_main_kb())
    await callback.answer()


@router.callback_query(OrderCB.filter(F.action == "repeat"))
async def order_repeat(callback: CallbackQuery, callback_data: OrderCB, state: FSMContext) -> None:
    found = await _own(callback, callback_data.order_id)
    if not found:
        return
    _, order = found
    async with async_session() as session:
        old_items = await crud.get_order_items(session, order.id)
        wanted = [(i.product_id, i.kind) for i in old_items] or [(order.product_id, "main")]
        current = {}
        for pid, kind in wanted:
            product = await crud.get_product(session, pid)
            if product is not None and product.is_active:
                current[kind if kind != "addon" else f"addon{pid}"] = (product, kind)

    main = current.get("main")
    if main is None:
        await callback.answer("Ця послуга зараз недоступна", show_alert=True)
        return
    cart = await checkout.build_cart(state, main[0])
    paid = current.get("paid")
    gift = current.get("gift")
    if paid:
        cart["paid"] = checkout._item(paid[0], "paid")
        if gift and float(gift[0].price) <= min(cart["main"]["price"], cart["paid"]["price"]):
            cart["gift"] = checkout._item(gift[0], "gift")
    cart["addons"] = [checkout._item(p, "addon") for k, (p, kind) in current.items() if kind == "addon"
                      and not (cart.get("main_tag") == "pin_included" and p.tag == "pin")]
    await state.update_data(cart=cart)
    await checkout.show_cart(callback, state)