"""SQLAlchemy async модель бази даних JOBIN-бота (SQLite) + автоматична міграція."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

import config
from timeutil import utcnow


class Base(DeclarativeBase):
    pass


class Manager(Base):
    """Менеджер зі своїм реферальним посиланням t.me/<бот>?start=m_<code>."""

    __tablename__ = "managers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    username: Mapped[str] = mapped_column(String(64))  # Telegram-юзернейм без @
    code: Mapped[str] = mapped_column(String(32), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    joined_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    manager_id: Mapped[int | None] = mapped_column(Integer, nullable=True)   # від якого менеджера прийшов
    referred_by: Mapped[int | None] = mapped_column(Integer, nullable=True)  # id клієнта, який запросив
    unsubscribed: Mapped[bool] = mapped_column(Boolean, default=False)      # відписався від розсилок
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)           # заблокував бота

    orders: Mapped[list["Order"]] = relationship(back_populates="user")


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    position: Mapped[int] = mapped_column(Integer, default=0)
    # package | single | addon  (addon — додаткові опції, пропонуються після вибору)
    kind: Mapped[str] = mapped_column(String(16), default="single")

    products: Mapped[list["Product"]] = relationship(back_populates="category")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[float] = mapped_column(Float, default=0)
    bonus: Mapped[str] = mapped_column(Text, default="")
    links: Mapped[str] = mapped_column(Text, default="")  # по одному в рядку
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    promo_eligible: Mapped[bool] = mapped_column(Boolean, default=False)  # акція 1+1=3
    tag: Mapped[str] = mapped_column(String(32), default="")  # pin_included | pin

    category: Mapped["Category"] = relationship(back_populates="products")


class Order(Base):
    """
    Статуси:
      pending_payment -> pending_review -> confirmed (чекаємо текст вакансії)
      -> awaiting_time (чекаємо вибір часу) -> in_work (у редактора) -> published
      rejected — оплату відхилено.
    """

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    status: Mapped[str] = mapped_column(String(32), default="pending_payment")
    amount: Mapped[float] = mapped_column(Float, default=0)         # до сплати (після знижки)
    subtotal: Mapped[float] = mapped_column(Float, default=0)       # сума до знижки
    discount_percent: Mapped[float] = mapped_column(Float, default=0)
    discount_source: Mapped[str] = mapped_column(String(64), default="")  # referral | promo:КОД
    promo_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    items_text: Mapped[str] = mapped_column(Text, default="")
    pay_note: Mapped[str] = mapped_column(Text, default="")         # напр. «≈ 10.85 USDT (курс 41.5)»
    receipt_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vacancy_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    publish_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)  # київський час
    time_note: Mapped[str] = mapped_column(String(16), default="")  # discuss | conflict
    post_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)  # UTC
    review_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    review_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    user: Mapped["User"] = relationship(back_populates="orders")
    product: Mapped["Product"] = relationship()


class OrderItem(Base):
    """Склад замовлення: основне розміщення, друге платне, подарунок, додаткові опції."""

    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    product_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(255))
    price: Mapped[float] = mapped_column(Float, default=0)
    kind: Mapped[str] = mapped_column(String(16), default="main")  # main | paid | gift | addon


class OrderNotification(Base):
    """Повідомлення адмінам про замовлення — щоб прибрати кнопки в усіх, коли один уже обробив."""

    __tablename__ = "order_notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(Integer, index=True)
    admin_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(Integer)
    caption: Mapped[str] = mapped_column(Text, default="")


class CartView(Base):
    """Слід перегляду послуги — для нагадування про покинутий кошик."""

    __tablename__ = "cart_views"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    viewed_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    reminded: Mapped[bool] = mapped_column(Boolean, default=False)
    reminded_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)


class Discount(Base):
    """Персональна знижка клієнта (за друга). Застосовується автоматично до наступного замовлення."""

    __tablename__ = "discounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)       # кому належить
    percent: Mapped[float] = mapped_column(Float, default=0)
    source: Mapped[str] = mapped_column(String(32), default="referral")
    friend_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # за кого нараховано
    used_order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class PromoCode(Base):
    __tablename__ = "promo_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    percent: Mapped[float] = mapped_column(Float, default=0)
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None — без обмежень
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class FsmState(Base):
    """Стан діалогу кожного користувача — зберігається в БД, тому переживає перезапуск бота."""

    __tablename__ = "fsm_states"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    state: Mapped[str | None] = mapped_column(String(128), nullable=True)
    data: Mapped[str] = mapped_column(Text, default="{}")


engine = create_async_engine(f"sqlite+aiosqlite:///{config.DB_PATH}")
async_session = async_sessionmaker(engine, expire_on_commit=False)


# (таблиця, колонка, тип) — додаються в уже існуючу базу, дані не втрачаються
MIGRATIONS = [
    ("users", "manager_id", "INTEGER"),
    ("users", "referred_by", "INTEGER"),
    ("users", "unsubscribed", "BOOLEAN DEFAULT 0"),
    ("users", "blocked", "BOOLEAN DEFAULT 0"),
    ("categories", "kind", "VARCHAR(16) DEFAULT 'single'"),
    ("products", "promo_eligible", "BOOLEAN DEFAULT 0"),
    ("products", "tag", "VARCHAR(32) DEFAULT ''"),
    ("orders", "subtotal", "FLOAT DEFAULT 0"),
    ("orders", "discount_percent", "FLOAT DEFAULT 0"),
    ("orders", "discount_source", "VARCHAR(64) DEFAULT ''"),
    ("orders", "promo_code", "VARCHAR(64)"),
    ("orders", "items_text", "TEXT DEFAULT ''"),
    ("orders", "pay_note", "TEXT DEFAULT ''"),
    ("orders", "publish_at", "DATETIME"),
    ("orders", "time_note", "VARCHAR(16) DEFAULT ''"),
    ("orders", "post_link", "TEXT"),
    ("orders", "published_at", "DATETIME"),
    ("orders", "review_requested", "BOOLEAN DEFAULT 0"),
    ("orders", "review_rating", "INTEGER"),
    ("orders", "review_comment", "TEXT"),
    ("cart_views", "reminded_at", "DATETIME"),
]


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)  # створює відсутні таблиці
        for table, column, ddl in MIGRATIONS:
            rows = (await conn.exec_driver_sql(f"PRAGMA table_info({table})")).fetchall()
            if column not in {r[1] for r in rows}:
                await conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        # дані зі старих версій
        await conn.exec_driver_sql("UPDATE orders SET subtotal = amount WHERE subtotal IS NULL OR subtotal = 0")
        await conn.exec_driver_sql(
            "UPDATE orders SET status = 'awaiting_time' "
            "WHERE status = 'confirmed' AND vacancy_text IS NOT NULL AND vacancy_text != ''"
        )
