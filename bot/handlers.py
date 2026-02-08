import logging

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message, MenuButtonDefault

from bot.config import API_URL, MINI_APP_URL
from bot.keyboards import get_main_keyboard

router = Router(name="main")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    # Сбрасываем кнопку «Открыть» в списке чатов при каждом /start
    try:
        await message.bot.set_chat_menu_button(menu_button=MenuButtonDefault())
    except Exception as e:
        logging.warning("Сброс кнопки меню: %s", e)

    await message.answer(
        "⚠️ Ведутся технические работы. Бот временно не работает.\n\n"
        "Приносим извинения за неудобства. Скоро всё заработает.",
        reply_markup=get_main_keyboard(MINI_APP_URL, API_URL),
    )
