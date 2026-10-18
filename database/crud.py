"""Функції роботи з БД (без прямого SQL у хендлерах)."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import config
from database.models import (
    CartView,
    Category,
    Discount,
    Manager,
    Order,
    OrderItem,
    OrderNotification,
    Product,
    PromoCode,
    User,
)
from timeutil import utcnow
from utils import fmt

PAID_STATUSES = ("confirmed", "awaiting_time", "in_work", "published")
ACTION_STATUSES = ("pending_payment", "confirmed", "awaiting_time")


# =====================  Користувачі  =====================

async def get_user_by_tg(session: AsyncSession, telegram_id: int) -> User | None:
    return (await session.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()


async def get_user(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def _touch_user(session: AsyncSession, user: User, username, full_name) -> None:
    changed = False
    if user.username != username:
        user.username, changed = username, True
    if user.full_name != full_name:
        user.full_name, changed = full_name, True
    if user.blocked:  # людина знову пише боту — отже, не заблокувала
        user.blocked, changed = False, True
    if changed:
        await session.commit()


async def get_or_create_user(
    session: AsyncSession, telegram_id: int, username: str | None, full_name: str | None
) -> User:
    user = await get_user_by_tg(session, telegram_id)
    if user is None:
        user = User(telegram_id=telegram_id, username=username, full_name=full_name)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    else:
        await _touch_user(session, user, username, full_name)
    return user


async def register_user(
    session: AsyncSession,
    telegram_id: int,
    username: str | None,
    full_name: str | None,
    manager_code: str | None = None,
    referrer_tg: int | None = None,
) -> tuple[User, bool]:
    """Реєстрація за /start. Менеджер і реферер запам'ятовуються лише для НОВИХ користувачів."""
    user = await get_user_by_tg(session, telegram_id)
    if user is not None:
        await _touch_user(session, user, username, full_name)
        return user, False

    manager = await get_manager_by_code(session, manager_code) if manager_code else None
    referrer = None
    if referrer_tg and referrer_tg != telegram_id:
        referrer = await get_user_by_tg(session, referrer_tg)

    user = User(
        telegram_id=telegram_id,
        username=username,
        full_name=full_name,
        manager_id=manager.id if manager else None,
        referred_by=referrer.id if referrer else None,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user, True


async def get_all_users(session: AsyncSession) -> list[User]:
    return list((await session.execute(select(User))).scalars().all())


async def set_unsubscribed(session: AsyncSession, telegram_id: int, value: bool) -> None:
    user = await get_user_by_tg(session, telegram_id)
    if user is not None:
        user.unsubscribed = value
        await session.commit()


async def mark_blocked(session: AsyncSession, telegram_id: int) -> None:
    user = await get_user_by_tg(session, telegram_id)
    if user is not None and not user.blocked:
        user.blocked = True
        await session.commit()


# =====================  Менеджери  =====================

async def get_managers(session: AsyncSession, only_active: bool = True) -> list[Manager]:
    stmt = select(Manager).order_by(Manager.id)
    if only_active:
        stmt = stmt.where(Manager.is_active.is_(True))
    return list((await session.execute(stmt)).scalars().all())


async def get_manager(session: AsyncSession, manager_id: int | None) -> Manager | None:
    return await session.get(Manager, manager_id) if manager_id else None


async def get_manager_by_code(session: AsyncSession, code: str) -> Manager | None:
    result = await session.execute(
        select(Manager).where(func.lower(Manager.code) == code.lower(), Manager.is_active.is_(True))
    )
    return result.scalar_one_or_none()


async def create_manager(session: AsyncSession, name: str, username: str, code: str) -> Manager:
    manager = Manager(name=name, username=username.lstrip("@"), code=code)
    session.add(manager)
    await session.commit()
    await session.refresh(manager)
    return manager


async def update_manager_field(session: AsyncSession, manager_id: int, field: str, value) -> None:
    manager = await session.get(Manager, manager_id)
    if manager is not None:
        setattr(manager, field, value)
        await session.commit()


async def manager_username_for(session: AsyncSession, user: User | None) -> str:
    """Юзернейм менеджера клієнта; якщо його не призначено — загальний із .env."""
    if user is not None and user.manager_id:
        manager = await session.get(Manager, user.manager_id)
        if manager is not None:
            return manager.username
    return config.MANAGER_USERNAME


# =====================  Каталог  =====================

async def get_categories(session: AsyncSession, include_addons: bool = False) -> list[Category]:
    """Для клієнта include_addons=False (додаткові опції пропонуються окремо), для адміна — True."""
    stmt = select(Category).order_by(Category.position)
    if not include_addons:
        stmt = stmt.where(Category.kind != "addon")
    return list((await session.execute(stmt)).scalars().all())


async def get_category(session: AsyncSession, category_id: int) -> Category | None:
    return await session.get(Category, category_id)


async def get_products_by_category(
    session: AsyncSession, category_id: int, only_active: bool = True
) -> list[Product]:
    stmt = select(Product).where(Product.category_id == category_id)
    if only_active:
        stmt = stmt.where(Product.is_active.is_(True))
    stmt = stmt.order_by(Product.position)
    return list((await session.execute(stmt)).scalars().all())


async def get_product(session: AsyncSession, product_id: int) -> Product | None:
    return await session.get(Product, product_id)


async def get_promo_products(session: AsyncSession) -> list[Product]:
    """Активні розміщення, що беруть участь в акції 1+1=3."""
    result = await session.execute(
        select(Product)
        .where(Product.promo_eligible.is_(True), Product.is_active.is_(True))
        .order_by(Product.position)
    )
    return list(result.scalars().all())


async def get_addons(session: AsyncSession) -> list[Product]:
    """Активні додаткові опції (Circle, Video Vacancy, Закріплення...)."""
    result = await session.execute(
        select(Product)
        .join(Category, Product.category_id == Category.id)
        .where(Category.kind == "addon", Product.is_active.is_(True))
        .order_by(Product.position)
    )
    return list(result.scalars().all())


async def create_product(session: AsyncSession, category_id: int, name: str) -> Product:
    product = Product(category_id=category_id, name=name, description="", price=0)
    session.add(product)
    await session.commit()
    await session.refresh(product)
    return product


async def update_product_field(session: AsyncSession, product_id: int, field: str, value) -> None:
    product = await session.get(Product, product_id)
    if product is not None:
        setattr(product, field, value)
        await session.commit()


async def toggle_product_active(session: AsyncSession, product_id: int) -> None:
    product = await session.get(Product, product_id)
    if product is not None:
        product.is_active = not product.is_active
        await session.commit()


async def toggle_product_promo(session: AsyncSession, product_id: int) -> None:
    product = await session.get(Product, product_id)
    if product is not None:
        product.promo_eligible = not product.promo_eligible
        await session.commit()


async def delete_product(session: AsyncSession, product_id: int) -> None:
    product = await session.get(Product, product_id)
    if product is not None:
        await session.delete(product)
        await session.commit()


# =====================  Замовлення  =====================

async def create_order_full(
    session: AsyncSession,
    user_id: int,
    items: list[dict],
    subtotal: float,
    percent: float,
    source: str,
    promo_code: str | None,
    discount_id: int | None,
) -> Order:
    """Створює замовлення зі складом, резервує знижку клієнта і використання промокоду."""
    amount = round(subtotal * (1 - percent / 100), 2)
    lines = []
    for it in items:
        if it["kind"] == "gift":
            lines.append(f"🎁 {it['name']} — у подарунок")
        else:
            lines.append(f"{it['name']} — {fmt(it['price'])} грн")
    main = next(i for i in items if i["kind"] == "main")

    order = Order(
        user_id=user_id,
        product_id=main["id"],
        status="pending_payment",
        amount=amount,
        subtotal=subtotal,
        discount_percent=percent,
        discount_source=source,
        promo_code=promo_code,
        items_text="\n".join(lines),
    )
    session.add(order)
    await session.flush()
    for it in items:
        session.add(
            OrderItem(order_id=order.id, product_id=it["id"], name=it["name"], price=it["price"], kind=it["kind"])
        )
    if discount_id:
        discount = await session.get(Discount, discount_id)
        if discount is not None:
            discount.used_order_id = order.id
    if promo_code:
        promo = await get_promo(session, promo_code)
        if promo is not None:
            promo.used_count += 1
    await session.commit()
    await session.refresh(order)
    return order


async def get_order(session: AsyncSession, order_id: int) -> Order | None:
    return await session.get(Order, order_id)


async def get_order_items(session: AsyncSession, order_id: int) -> list[OrderItem]:
    result = await session.execute(select(OrderItem).where(OrderItem.order_id == order_id).order_by(OrderItem.id))
    return list(result.scalars().all())


async def get_items_for_orders(session: AsyncSession, order_ids: list[int]) -> dict[int, list[OrderItem]]:
    out: dict[int, list[OrderItem]] = {oid: [] for oid in order_ids}
    if not order_ids:
        return out
    result = await session.execute(
        select(OrderItem).where(OrderItem.order_id.in_(order_ids)).order_by(OrderItem.id)
    )
    for item in result.scalars().all():
        out[item.order_id].append(item)
    return out


async def count_user_orders(session: AsyncSession, user_id: int) -> int:
    return (await session.execute(select(func.count(Order.id)).where(Order.user_id == user_id))).scalar_one()


async def get_user_orders(
    session: AsyncSession, user_id: int, offset: int = 0, limit: int | None = None
) -> list[Order]:
    stmt = select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc(), Order.id.desc())
    if limit is not None:
        stmt = stmt.offset(offset).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


async def get_pending_action_order(session: AsyncSession, user_id: int) -> Order | None:
    """Останнє замовлення клієнта, яке чекає на його дію (оплата / вакансія / вибір часу)."""
    result = await session.execute(
        select(Order)
        .where(Order.user_id == user_id, Order.status.in_(ACTION_STATUSES))
        .order_by(Order.created_at.desc(), Order.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def set_pay_note(session: AsyncSession, order_id: int, note: str) -> None:
    order = await session.get(Order, order_id)
    if order is not None:
        order.pay_note = note
        await session.commit()


async def attach_receipt(session: AsyncSession, order_id: int, file_id: str) -> None:
    order = await session.get(Order, order_id)
    if order is not None:
        order.receipt_file_id = file_id
        order.status = "pending_review"
        await session.commit()


async def set_order_status(session: AsyncSession, order_id: int, status: str, reason: str | None = None) -> None:
    order = await session.get(Order, order_id)
    if order is not None:
        order.status = status
        if reason is not None:
            order.reject_reason = reason
        await session.commit()


async def set_vacancy_text(session: AsyncSession, order_id: int, text: str) -> None:
    order = await session.get(Order, order_id)
    if order is not None:
        order.vacancy_text = text
        await session.commit()


async def set_publish_time(
    session: AsyncSession, order_id: int, when: dt.datetime | None, status: str, time_note: str = ""
) -> None:
    order = await session.get(Order, order_id)
    if order is not None:
        order.publish_at = when
        order.status = status
        order.time_note = time_note
        await session.commit()


async def set_time_note(session: AsyncSession, order_id: int, note: str) -> None:
    order = await session.get(Order, order_id)
    if order is not None:
        order.time_note = note
        await session.commit()


async def mark_published(session: AsyncSession, order_id: int, link: str | None) -> None:
    order = await session.get(Order, order_id)
    if order is not None:
        order.status = "published"
        order.published_at = utcnow()
        order.post_link = link
        order.time_note = ""
        await session.commit()


async def get_slot_conflicts(session: AsyncSession, when: dt.datetime, exclude_order_id: int) -> list[Order]:
    """Інші замовлення, вже заплановані на цей самий час (1 вакансія на слот)."""
    result = await session.execute(
        select(Order).where(
            Order.status == "in_work", Order.publish_at == when, Order.id != exclude_order_id
        )
    )
    return list(result.scalars().all())


async def get_queue(session: AsyncSession) -> list[Order]:
    result = await session.execute(
        select(Order).where(Order.status == "in_work").order_by(Order.publish_at.is_(None), Order.publish_at, Order.id)
    )
    return list(result.scalars().all())


async def release_order_benefits(session: AsyncSession, order: Order) -> None:
    """Замовлення відхилено — повертаємо клієнту знижку й використання промокоду."""
    result = await session.execute(select(Discount).where(Discount.used_order_id == order.id))
    for discount in result.scalars().all():
        discount.used_order_id = None
    if order.promo_code:
        promo = await get_promo(session, order.promo_code)
        if promo is not None and promo.used_count > 0:
            promo.used_count -= 1
    await session.commit()


# ----- повідомлення адмінам про замовлення -----

async def save_notification(session: AsyncSession, order_id: int, admin_id: int, message_id: int, caption: str) -> None:
    session.add(OrderNotification(order_id=order_id, admin_id=admin_id, message_id=message_id, caption=caption))
    await session.commit()


async def get_notifications(session: AsyncSession, order_id: int) -> list[OrderNotification]:
    result = await session.execute(select(OrderNotification).where(OrderNotification.order_id == order_id))
    return list(result.scalars().all())


# =====================  Покинутий кошик  =====================

async def add_cart_view(session: AsyncSession, user_id: int, product_id: int) -> CartView:
    """Фіксує перегляд. Якщо ту саму послугу вже дивились і нагадування ще не було — нового запису не створюємо."""
    existing = (
        await session.execute(
            select(CartView).where(
                CartView.user_id == user_id,
                CartView.product_id == product_id,
                CartView.resolved.is_(False),
                CartView.reminded.is_(False),
            )
        )
    ).scalars().first()
    if existing is not None:
        return existing
    view = CartView(user_id=user_id, product_id=product_id)
    session.add(view)
    await session.commit()
    await session.refresh(view)
    return view


async def resolve_user_cart_views(session: AsyncSession, user_id: int) -> None:
    """Клієнт надіслав квитанцію — нагадування більше не потрібні."""
    result = await session.execute(
        select(CartView).where(CartView.user_id == user_id, CartView.resolved.is_(False))
    )
    for view in result.scalars().all():
        view.resolved = True
    await session.commit()


async def get_due_cart_views(session: AsyncSession, cutoff: dt.datetime) -> list[CartView]:
    result = await session.execute(
        select(CartView).where(
            CartView.resolved.is_(False), CartView.reminded.is_(False), CartView.viewed_at <= cutoff
        )
    )
    return list(result.scalars().all())


async def recently_reminded(session: AsyncSession, user_id: int, since: dt.datetime) -> bool:
    result = await session.execute(
        select(func.count(CartView.id)).where(CartView.user_id == user_id, CartView.reminded_at >= since)
    )
    return result.scalar_one() > 0


# =====================  Знижки та промокоди  =====================

async def get_available_discount(session: AsyncSession, user_id: int) -> Discount | None:
    """Найбільша вільна знижка клієнта (також ті, що «зависли» на неоплачених замовленнях)."""
    free = (
        await session.execute(
            select(Discount)
            .where(Discount.user_id == user_id, Discount.used_order_id.is_(None))
            .order_by(Discount.percent.desc())
        )
    ).scalars().first()
    stale = (
        await session.execute(
            select(Discount)
            .join(Order, Discount.used_order_id == Order.id)
            .where(Discount.user_id == user_id, Order.status == "pending_payment")
            .order_by(Discount.percent.desc())
        )
    ).scalars().first()
    candidates = [d for d in (free, stale) if d is not None]
    return max(candidates, key=lambda d: d.percent) if candidates else None


async def count_free_discounts(session: AsyncSession, user_id: int) -> int:
    return (
        await session.execute(
            select(func.count(Discount.id)).where(Discount.user_id == user_id, Discount.used_order_id.is_(None))
        )
    ).scalar_one()


async def grant_referral_reward(session: AsyncSession, friend: User) -> tuple[Discount, User] | None:
    """Друг оплатив перше замовлення — той, хто його привів, отримує знижку (один раз за друга)."""
    if not friend.referred_by:
        return None
    already = (
        await session.execute(select(Discount).where(Discount.friend_user_id == friend.id))
    ).scalars().first()
    if already is not None:
        return None
    referrer = await session.get(User, friend.referred_by)
    if referrer is None:
        return None
    discount = Discount(
        user_id=referrer.id, percent=config.REFERRAL_PERCENT, source="referral", friend_user_id=friend.id
    )
    session.add(discount)
    await session.commit()
    await session.refresh(discount)
    return discount, referrer


async def get_promo(session: AsyncSession, code: str) -> PromoCode | None:
    result = await session.execute(select(PromoCode).where(PromoCode.code == code.strip().upper()))
    return result.scalar_one_or_none()


async def list_promos(session: AsyncSession) -> list[PromoCode]:
    return list((await session.execute(select(PromoCode).order_by(PromoCode.id.desc()))).scalars().all())


async def create_promo(session: AsyncSession, code: str, percent: float, max_uses: int | None) -> PromoCode:
    promo = PromoCode(code=code.strip().upper(), percent=percent, max_uses=max_uses)
    session.add(promo)
    await session.commit()
    await session.refresh(promo)
    return promo


async def toggle_promo_active(session: AsyncSession, promo_id: int) -> None:
    promo = await session.get(PromoCode, promo_id)
    if promo is not None:
        promo.is_active = not promo.is_active
        await session.commit()


async def delete_promo(session: AsyncSession, promo_id: int) -> None:
    promo = await session.get(PromoCode, promo_id)
    if promo is not None:
        await session.delete(promo)
        await session.commit()


async def user_used_promo(session: AsyncSession, user_id: int, code: str) -> bool:
    result = await session.execute(
        select(func.count(Order.id)).where(
            Order.user_id == user_id, Order.promo_code == code.strip().upper(), Order.status != "rejected"
        )
    )
    return result.scalar_one() > 0
