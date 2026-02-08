import asyncio
import logging

import uvicorn

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(name)s: %(message)s")
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import MenuButtonDefault

from bot.config import API_URL, BOT_TOKEN
from bot.handlers import router


async def main() -> None:
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN не задан. Создайте .env файл на основе .env.example")

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)

    # Убираем кнопку «Открыть» в списке чатов — остаётся только «Личный кабинет» в чате
    try:
        await bot.set_chat_menu_button(menu_button=MenuButtonDefault())
    except Exception as e:
        logging.warning("Не удалось сбросить кнопку меню бота: %s", e)

    # API для Mini App
    host = "0.0.0.0"
    port = 8000
    try:
        from urllib.parse import urlparse
        parsed = urlparse(API_URL)
        if parsed.port:
            port = parsed.port
    except Exception:
        pass

    config = uvicorn.Config("api.main:app", host=host, port=port)
    server = uvicorn.Server(config)
    api_task = asyncio.create_task(server.serve())

    try:
        await dp.start_polling(bot)
    finally:
        api_task.cancel()
        try:
            await api_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    asyncio.run(main())
