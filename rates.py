"""Курс USDT -> UAH для автоматичного розрахунку суми оплати в крипті.

Джерело: офіційний курс НБУ для USD (USDT прив'язаний до долара 1:1).
Binance з 28.09.2026 більше не торгує парою USDT/UAH, тому ринковий курс звідти не береться.

Налаштування в .env:
  USDT_RATE            — свій фіксований курс (якщо вказано, НБУ не опитується)
  USDT_MARKUP_PERCENT  — надбавка до курсу НБУ у відсотках
"""
from __future__ import annotations

import logging
import time
from decimal import ROUND_UP, Decimal

import aiohttp

import config

log = logging.getLogger(__name__)

# Основне посилання НБУ + запасне (старий формат того ж API)
NBU_URLS = [
    "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchangenew?json&valcode=USD",
    "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?valcode=USD&json",
]

CACHE_TTL = 10 * 60        # курс оновлюється не частіше, ніж раз на 10 хвилин
STALE_MAX = 24 * 60 * 60   # якщо НБУ недоступний — використовуємо останній відомий курс до 24 год

_cache: dict = {"rate": None, "ts": 0.0}


async def _fetch_nbu_rate() -> float | None:
    timeout = aiohttp.ClientTimeout(total=8)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for url in NBU_URLS:
            try:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json(content_type=None)
                for row in data:
                    if str(row.get("cc", "")).upper() == "USD" and float(row.get("rate", 0)) > 0:
                        return float(row["rate"])
            except Exception as exc:  # мережа/формат — пробуємо наступне посилання
                log.warning("Не вдалося отримати курс НБУ (%s): %s", url, exc)
    return None


async def get_usdt_rate() -> float | None:
    """Скільки гривень за 1 USDT. None — якщо курс отримати не вдалося."""
    if config.USDT_RATE > 0:
        return config.USDT_RATE

    now = time.time()
    if _cache["rate"] and now - _cache["ts"] < CACHE_TTL:
        base = _cache["rate"]
    else:
        fresh = await _fetch_nbu_rate()
        if fresh:
            _cache["rate"], _cache["ts"] = fresh, now
            base = fresh
        elif _cache["rate"] and now - _cache["ts"] < STALE_MAX:
            base = _cache["rate"]
        else:
            return None
    return round(base * (1 + config.USDT_MARKUP_PERCENT / 100), 2)


def uah_to_usdt(amount_uah: float, rate: float) -> Decimal:
    """Сума в USDT, округлена ВГОРУ до центів — щоб клієнт випадково не недоплатив."""
    return (Decimal(str(amount_uah)) / Decimal(str(rate))).quantize(Decimal("0.01"), rounding=ROUND_UP)
