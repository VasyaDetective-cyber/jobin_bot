"""Завантаження налаштувань бота зі змінних середовища (.env)."""
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

ADMIN_IDS: list[int] = [
    int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()
]

PAYMENT_CARD: str = os.getenv("PAYMENT_CARD", "не вказано")
PAYMENT_IBAN: str = os.getenv("PAYMENT_IBAN", "не вказано")
PAYMENT_CRYPTO: str = os.getenv("PAYMENT_CRYPTO", "")  # USDT TRC-20, необов'язково
MANAGER_USERNAME: str = os.getenv("MANAGER_USERNAME", "jobin_manager").strip().lstrip("@")


def _float_env(name: str, default: float = 0.0) -> float:
    raw = os.getenv(name, "").strip().replace(",", ".")
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


USDT_RATE: float = _float_env("USDT_RATE")                       # 0 = брати курс НБУ автоматично
USDT_MARKUP_PERCENT: float = _float_env("USDT_MARKUP_PERCENT")   # надбавка до курсу, %
DB_PATH: str = os.getenv("DB_PATH", "jobin.db")

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN не задано. Скопіюйте .env.example у .env та вкажіть токен бота."
    )

if not ADMIN_IDS:
    print("[УВАГА] ADMIN_IDS порожній — жоден користувач не матиме доступу до /admin.")


# ---------- Редактор, рефералка, графік ----------

def _int_env(name: str, default: int = 0) -> int:
    raw = os.getenv(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


# Telegram ID редактора, якому надсилаються вакансії. Порожньо/0 — вакансії йдуть усім адмінам.
EDITOR_ID: int = _int_env("EDITOR_ID")
# Знижка (%) для того, хто привів друга, після першої оплати друга
REFERRAL_PERCENT: float = _float_env("REFERRAL_PERCENT", 40.0)

TIMEZONE: str = os.getenv("TIMEZONE", "Europe/Kyiv")
SLOT_HOURS: tuple[int, ...] = (8, 10, 12, 14, 18, 20)  # графік публікацій; 20:00 — останній
SCHEDULE_DAYS: int = 14           # на скільки днів уперед можна планувати
MIN_LEAD_MINUTES: int = 60        # мінімум часу до публікації
ABANDONED_DELAY_HOURS: int = 2    # через скільки нагадувати про покинутий кошик
REVIEW_DELAY_DAYS: int = 3        # через скільки днів після публікації питати про результат
MESSAGE_WINDOW: tuple[int, int] = (9, 21)  # автоповідомлення лише з 9:00 до 21:00
BACKUP_HOUR: int = 3              # о котрій надсилати резервну копію бази

STAFF_IDS: set[int] = set(ADMIN_IDS) | ({EDITOR_ID} if EDITOR_ID else set())
