import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeChat, ErrorEvent

import app_state
import config
from database.models import async_session, init_db
from database.seed import seed_initial_data, seed_managers
from handlers import (
    admin, admin_catalog, admin_crm, admin_promo, admin_tools, checkout, common,
    orders, referral, reviews, support, user, vacancy,
)
from scheduler import scheduler, setup_jobs
from storage import SQLiteStorage

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("jobin")

CLIENT_COMMANDS = [
    BotCommand(command="menu", description="🏠 Головне меню"),
    BotCommand(command="orders", description="🗂 Мої замовлення"),
    BotCommand(command="manager", description="💬 Зв'язок з менеджером"),
]


async def setup_commands(bot: Bot) -> None:
    await bot.set_my_commands(CLIENT_COMMANDS)
    staff = {**{a: True for a in config.ADMIN_IDS}}
    if config.EDITOR_ID:
        staff.setdefault(config.EDITOR_ID, False)
    for chat_id, is_admin in staff.items():
        commands = list(CLIENT_COMMANDS) + [BotCommand(command="queue", description="📋 Черга публікацій")]
        if is_admin:
            commands.append(BotCommand(command="admin", description="🛠 Адмін-панель"))
        try:
            await bot.set_my_commands(commands, scope=BotCommandScopeChat(chat_id=chat_id))
        except Exception:
            pass


async def on_error(event: ErrorEvent, bot: Bot) -> bool:
    log.exception("Помилка в обробнику: %s", event.exception)
    update = event.update
    try:
        if update.callback_query:
            await update.callback_query.answer("Щось пішло не так. Спробуйте ще раз або натисніть «🏠 Меню».", show_alert=True)
        elif update.message:
            await update.message.answer("Ой, щось пішло не так 😔 Спробуйте ще раз або натисніть «🏠 Меню».")
    except Exception:
        pass
    if config.ADMIN_IDS:
        try:
            await bot.send_message(config.ADMIN_IDS[0], f"⚠️ Помилка в боті: {type(event.exception).__name__}: {event.exception}"[:500])
        except Exception:
            pass
    return True


async def main() -> None:
    await init_db()
    async with async_session() as session:
        await seed_initial_data(session)
        await seed_managers(session)

    bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    app_state.bot_username = (await bot.get_me()).username or ""
    dp = Dispatcher(storage=SQLiteStorage())
    dp.errors.register(on_error)

    for module in (
        common, admin, admin_catalog, admin_crm, admin_promo, admin_tools, checkout,
        orders, vacancy, support, reviews, referral, user,
    ):
        dp.include_router(module.router)

    await setup_commands(bot)
    setup_jobs(bot)
    scheduler.start()

    await bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())