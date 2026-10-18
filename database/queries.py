"""Статистика, сегменти для розсилки та дані для Excel."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.crud import PAID_STATUSES
from database.models import CartView, Discount, Manager, Order, OrderItem, User
from timeutil import local_to_utc, now_local, utc_to_local, utcnow
from utils import fmt

SEGMENTS = {
    "all": "Усім",
    "buyers": "Лише покупцям",
    "nonbuyers": "Лише тим, хто не купував",
    "inactive7": "Не замовляли останні 7 днів",
    "manager": "За менеджером",
}


# =====================  Сегменти розсилки  =====================

async def segment_users(session: AsyncSession, seg: str, manager_id: int | None = None) -> list[User]:
    """Отримувачі розсилки. Ті, хто відписався або заблокував бота, не потрапляють ніколи."""
    stmt = select(User).where(User.unsubscribed.is_(False), User.blocked.is_(False))
    paid_ids = select(Order.user_id).where(Order.status.in_(PAID_STATUSES))
    if seg == "buyers":
        stmt = stmt.where(User.id.in_(paid_ids))
    elif seg == "nonbuyers":
        stmt = stmt.where(User.id.not_in(paid_ids))
    elif seg == "inactive7":
        recent = select(Order.user_id).where(
            Order.status.in_(PAID_STATUSES), Order.created_at >= utcnow() - dt.timedelta(days=7)
        )
        stmt = stmt.where(User.id.not_in(recent))
    elif seg == "manager":
        stmt = stmt.where(User.manager_id == manager_id)
    return list((await session.execute(stmt.order_by(User.id))).scalars().all())


# =====================  Статистика  =====================

PERIODS = {"today": "Сьогодні", "7d": "7 днів", "30d": "30 днів", "all": "Весь час"}


def period_start(period: str) -> dt.datetime | None:
    """Початок періоду в UTC (None — весь час)."""
    if period == "today":
        midnight = now_local().replace(hour=0, minute=0, second=0, microsecond=0)
        return local_to_utc(midnight)
    if period == "7d":
        return utcnow() - dt.timedelta(days=7)
    if period == "30d":
        return utcnow() - dt.timedelta(days=30)
    return None


def _pct(part: int, whole: int) -> str:
    return f"{round(part * 100 / whole)}%" if whole else "—"


async def stats_text(session: AsyncSession, period: str) -> str:
    start = period_start(period)

    def since(column):
        return [column >= start] if start is not None else []

    async def scalar(stmt):
        return (await session.execute(stmt)).scalar_one() or 0

    total_users = await scalar(select(func.count(User.id)))
    new_users = await scalar(select(func.count(User.id)).where(*since(User.joined_at)))
    viewers = await scalar(select(func.count(distinct(CartView.user_id))).where(*since(CartView.viewed_at)))

    orders_all = await scalar(select(func.count(Order.id)).where(*since(Order.created_at)))
    buyers_created = await scalar(select(func.count(distinct(Order.user_id))).where(*since(Order.created_at)))
    paid_where = [Order.status.in_(PAID_STATUSES), *since(Order.created_at)]
    paid_orders = await scalar(select(func.count(Order.id)).where(*paid_where))
    paid_users = await scalar(select(func.count(distinct(Order.user_id))).where(*paid_where))
    revenue = await scalar(select(func.sum(Order.amount)).where(*paid_where))
    discounts = await scalar(
        select(func.sum(Order.subtotal - Order.amount)).where(*paid_where, Order.subtotal > 0)
    )
    avg_check = revenue / paid_orders if paid_orders else 0

    lines = [f"📊 <b>Статистика · {PERIODS[period]}</b>", ""]
    lines += [
        "👥 <b>Клієнти</b>",
        f"Усього в базі: {total_users} · нових за період: {new_users}",
        "",
        "🔻 <b>Воронка</b> (унікальні клієнти)",
        f"Переглянули послугу: {viewers}",
        f"Оформили замовлення: {buyers_created} ({_pct(buyers_created, viewers)})",
        f"Оплатили: {paid_users} ({_pct(paid_users, buyers_created)})",
        "",
        "💰 <b>Гроші</b>",
        f"Замовлень оформлено: {orders_all} · оплачено: {paid_orders}",
        f"Дохід: <b>{fmt(revenue)} грн</b> · середній чек: {fmt(avg_check)} грн",
        f"Надано знижок: {fmt(discounts)} грн",
    ]

    # популярні послуги
    top_stmt = (
        select(OrderItem.name, func.count(OrderItem.id).label("cnt"))
        .join(Order, OrderItem.order_id == Order.id)
        .where(*paid_where)
        .group_by(OrderItem.name)
        .order_by(func.count(OrderItem.id).desc())
        .limit(5)
    )
    top = (await session.execute(top_stmt)).all()
    lines += ["", "🏆 <b>Найпопулярніші послуги</b>"]
    lines += [f"{i}. {name} — {cnt}" for i, (name, cnt) in enumerate(top, 1)] or ["—"]

    # менеджери
    managers = list((await session.execute(select(Manager).order_by(Manager.id))).scalars().all())
    lines += ["", "🧑‍💼 <b>Менеджери</b> (клієнти → оплачені замовлення → дохід)"]
    for m in managers:
        clients = await scalar(select(func.count(User.id)).where(User.manager_id == m.id))
        cnt = await scalar(
            select(func.count(Order.id)).join(User, Order.user_id == User.id).where(User.manager_id == m.id, *paid_where)
        )
        rev = await scalar(
            select(func.sum(Order.amount)).join(User, Order.user_id == User.id).where(User.manager_id == m.id, *paid_where)
        )
        lines.append(f"{m.name}: {clients} → {cnt} → {fmt(rev)} грн")
    if not managers:
        lines.append("—")

    # рефералка
    invited = await scalar(select(func.count(User.id)).where(User.referred_by.is_not(None), *since(User.joined_at)))
    rewards = await scalar(select(func.count(Discount.id)).where(*since(Discount.created_at)))
    lines += ["", "🎁 <b>Запрошення друзів</b>", f"Прийшло за запрошенням: {invited} · знижок нараховано: {rewards}"]

    # відгуки
    published_where = [Order.review_rating.is_not(None)]
    if start is not None:
        published_where.append(Order.published_at >= start)
    rev_cnt = await scalar(select(func.count(Order.id)).where(*published_where))
    rev_avg = await scalar(select(func.avg(Order.review_rating)).where(*published_where))
    lines += ["", "⭐ <b>Відгуки</b>", f"Оцінок: {rev_cnt}" + (f" · середня: {rev_avg:.1f} з 3" if rev_cnt else "")]
    return "\n".join(lines)


# =====================  Дані для Excel  =====================

ORDER_STATUS_UA = {
    "pending_payment": "Очікує оплати",
    "pending_review": "Перевірка оплати",
    "confirmed": "Оплачено, чекаємо вакансію",
    "awaiting_time": "Чекаємо вибір часу",
    "in_work": "У редактора",
    "published": "Опубліковано",
    "rejected": "Відхилено",
}


async def export_rows(session: AsyncSession) -> tuple[list[list], list[list]]:
    users = list((await session.execute(select(User).order_by(User.id))).scalars().all())
    managers = {m.id: m.name for m in (await session.execute(select(Manager))).scalars().all()}
    orders = list((await session.execute(select(Order).order_by(Order.id))).scalars().all())
    items = list((await session.execute(select(OrderItem).order_by(OrderItem.id))).scalars().all())

    items_by_order: dict[int, list[OrderItem]] = {}
    for it in items:
        items_by_order.setdefault(it.order_id, []).append(it)
    orders_by_user: dict[int, list[Order]] = {}
    for o in orders:
        orders_by_user.setdefault(o.user_id, []).append(o)
    invited: dict[int, int] = {}
    for u in users:
        if u.referred_by:
            invited[u.referred_by] = invited.get(u.referred_by, 0) + 1

    def names(order: Order) -> list[str]:
        found = items_by_order.get(order.id)
        return [i.name for i in found] if found else [l.split(" — ")[0] for l in (order.items_text or "").splitlines() if l]

    clients: list[list] = []
    for u in users:
        paid = [o for o in orders_by_user.get(u.id, []) if o.status in PAID_STATUSES]
        bought: list[str] = []
        for o in paid:
            for n in names(o):
                if n not in bought:
                    bought.append(n)
        last = max((o.created_at for o in paid), default=None)
        if u.blocked:
            sub = "Заблокував бота"
        elif u.unsubscribed:
            sub = "Відписався від розсилки"
        else:
            sub = "Підписаний"
        clients.append([
            u.telegram_id,
            f"@{u.username}" if u.username else "",
            u.full_name or "",
            managers.get(u.manager_id, ""),
            utc_to_local(u.joined_at).strftime("%d.%m.%Y %H:%M") if u.joined_at else "",
            len(paid),
            sum(o.amount for o in paid),
            utc_to_local(last).strftime("%d.%m.%Y") if last else "",
            ", ".join(bought),
            invited.get(u.id, 0),
            sub,
        ])

    user_by_id = {u.id: u for u in users}
    order_rows: list[list] = []
    for o in orders:
        u = user_by_id.get(o.user_id)
        order_rows.append([
            o.id,
            utc_to_local(o.created_at).strftime("%d.%m.%Y %H:%M"),
            (f"@{u.username}" if u and u.username else (str(u.telegram_id) if u else "")),
            managers.get(u.manager_id, "") if u else "",
            "; ".join(names(o)),
            o.subtotal or o.amount,
            o.discount_percent or 0,
            o.amount,
            ORDER_STATUS_UA.get(o.status, o.status),
            o.publish_at.strftime("%d.%m.%Y %H:%M") if o.publish_at else "",
            o.post_link or "",
            o.review_rating or "",
        ])
    return clients, order_rows


CLIENT_HEADERS = [
    "Telegram ID", "Username", "Ім'я", "Менеджер", "Дата приєднання", "Оплачених замовлень",
    "Сума оплачених, грн", "Остання покупка", "Що купував", "Запросив друзів", "Розсилка",
]
ORDER_HEADERS = [
    "№", "Створено", "Клієнт", "Менеджер", "Склад", "Сума до знижки", "Знижка, %", "До сплати, грн",
    "Статус", "Час публікації", "Посилання на пост", "Оцінка (1-3)",
]
