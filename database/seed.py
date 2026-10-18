"""Первинне наповнення каталогу (комерційна пропозиція JOBIN).

Усі ціни та описи потім можна змінювати через /admin -> Каталог послуг.
Це наповнення виконується лише один раз — коли база порожня.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Category, Product

SITE_URL = "https://jobin.up.railway.app/"
MAIN_CHANNEL = "https://t.me/+gz5NTCGE1y0xMDQy"
INSTAGRAM = "https://www.instagram.com/jobin_com1?igsh=bDZldTdod3Yyb3Yz"

# Резервні посилання на канали мережі (розділ 4.2 ТЗ).
# УВАГА: яке посилання якому каналу належить, у ТЗ не вказано — призначено орієнтовно.
# Перевірте й за потреби виправте: /admin -> Каталог послуг -> послуга -> Посилання.
L1, L2, L3, L4, L5, L6 = (
    "https://t.me/+8fhUBKD6QeNlOTdi",
    "https://t.me/+RJJiHQWhEbVlMTEy",
    "https://t.me/+jpuF3IGCmbMyYjMy",
    "http://t.me/robotaonlain4728",
    "https://t.me/+RxnVhKAHoSk5ZjFi",
    "https://t.me/+xrXZ8GOUCRhmY2Nl",
)

# Посилання окремих каналів (використовуються і в окремих розміщеннях, і в пакетах)
LINKS = {
    "Work In Ukraine": L1,
    "Work Up": L2,
    "Remote": L3,
    "Робота дистанційно": L5,
    "Telegram Jobin": MAIN_CHANNEL,
    "Сайт JobIn": SITE_URL,
    "Instagram JobIn.Company": INSTAGRAM,
    "Telegram-розсилка (60 000+ кандидатів)": L6,
}

PACKAGE_BONUS = (
    "🎁 У кожному пакеті:\n"
    "✓ оформлення вакансії під формат каналів\n"
    "✓ додаткове безкоштовне розміщення в TikTok"
)

# (назва, ціна, опис, теги, склад пакета для посилань)
PACKAGES = [
    (
        "START",
        1490,
        "• Work Up\n• Telegram-канал JobIn\n• сайт JobIn\n• Work Up bot",
        "",
        ["Work Up", "Telegram Jobin", "Сайт JobIn"],
    ),
    (
        "BUSINESS ⭐",
        1990,
        "⭐ Оптимальний вибір\n\n• Work Up\n• Work In Ukraine\n• Remote\n• Telegram Jobin\n• безкоштовне закріплення",
        "pin_included",
        ["Work Up", "Work In Ukraine", "Remote", "Telegram Jobin"],
    ),
    (
        "PRO",
        2490,
        "• Work Up\n• Remote\n• Telegram-канал JobIn\n• сайт JobIn\n• Instagram JobIn\n• Work In",
        "",
        ["Work Up", "Remote", "Telegram Jobin", "Сайт JobIn", "Instagram JobIn.Company", "Work In Ukraine"],
    ),
    (
        "MAX",
        3990,
        "МАКСИМАЛЬНЕ ОХОПЛЕННЯ 💥\nМаксимальне розміщення вакансії\n\nУ пакет входить все:\n\n"
        "• Work Up\n• Remote\n• Telegram-канал JobIn\n• сайт JobIn\n• Instagram JobIn\n"
        "• Work In\n• Jobin bot\n• Work Up bot\n• Безкоштовне закріплення",
        "pin_included",
        ["Work Up", "Remote", "Telegram Jobin", "Сайт JobIn", "Instagram JobIn.Company", "Work In Ukraine"],
    ),
]

# (назва, ціна, опис, бонус, бере участь в акції 1+1=3)
SINGLES = [
    (
        "Work In Ukraine",
        750,
        "Розміщення вакансії в каналі Work In Ukraine.",
        "🎁 + безкоштовне розміщення в каналах «Робота дистанційно» та «Вакансмен»",
        True,
    ),
    ("Work Up", 700, "Розміщення вакансії в каналі Work Up.", "", True),
    ("Remote", 495, "Розміщення вакансії в каналі Remote.", "", True),
    ("Робота дистанційно", 350, "Розміщення вакансії в каналі «Робота дистанційно».", "", True),
    ("Telegram Jobin", 350, "Розміщення вакансії в Telegram-каналі JobIn.", "", True),
    ("Сайт JobIn", 350, "Розміщення вакансії на сайті JobIn.", "", True),
    ("Instagram JobIn.Company", 450, "Розміщення вакансії в Instagram JobIn.Company.", "", True),
    (
        "Telegram-розсилка (60 000+ кандидатів)",
        1400,
        "Розсилка вашої вакансії в Telegram по базі 60 000+ кандидатів.",
        "",
        False,  # розсилка не входить в акцію 1+1=3
    ),
]

# (назва, ціна, опис, тег)
ADDONS = [
    (
        "Circle",
        400,
        "Коротке відео-кружечок від редактора після основної публікації вакансії. "
        "Живий формат допомагає додатково привернути увагу кандидатів та підсилити основний пост.",
        "",
    ),
    (
        "Video Vacancy",
        500,
        "Окреме вертикальне відео про вакансію для Reels / TikTok.",
        "",
    ),
    (
        "Закріплення",
        200,
        "Додаткове закріплення вакансії на майданчику.",
        "pin",
    ),
]


async def seed_initial_data(session: AsyncSession) -> None:
    existing = (await session.execute(select(Category.id))).first()
    if existing:
        return  # каталог вже наповнено, повторно не сіємо

    cat_pkg = Category(name="Пакетні розміщення", position=0, kind="package")
    cat_single = Category(name="Окремі розміщення", position=1, kind="single")
    cat_addon = Category(name="Додаткові опції", position=2, kind="addon")
    session.add_all([cat_pkg, cat_single, cat_addon])
    await session.flush()  # отримати id категорій

    for pos, (name, price, desc, tag, components) in enumerate(PACKAGES):
        links = []
        for c in components:
            link = LINKS.get(c)
            if link and link not in links:
                links.append(link)
        session.add(
            Product(
                category_id=cat_pkg.id,
                name=name,
                description=desc,
                price=price,
                bonus=PACKAGE_BONUS,
                links="\n".join(links),
                tag=tag,
                position=pos,
            )
        )

    for pos, (name, price, desc, bonus, promo) in enumerate(SINGLES):
        session.add(
            Product(
                category_id=cat_single.id,
                name=name,
                description=desc,
                price=price,
                bonus=bonus,
                links=LINKS.get(name, ""),
                promo_eligible=promo,
                position=pos,
            )
        )

    for pos, (name, price, desc, tag) in enumerate(ADDONS):
        session.add(
            Product(
                category_id=cat_addon.id,
                name=name,
                description=desc,
                price=price,
                tag=tag,
                position=pos,
            )
        )

    await session.commit()


# Заглушки менеджерів — замініть на справжніх у /admin -> Менеджери (без правки коду)
PLACEHOLDER_MANAGERS = [
    ("Менеджер 1", "manager_one", "m1"),
    ("Менеджер 2", "manager_two", "m2"),
]


async def seed_managers(session: AsyncSession) -> None:
    from database.models import Manager

    if (await session.execute(select(Manager.id))).first():
        return
    for name, username, code in PLACEHOLDER_MANAGERS:
        session.add(Manager(name=name, username=username, code=code))
    await session.commit()
