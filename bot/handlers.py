from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot.config import MINI_APP_URL
from bot.keyboards import get_main_keyboard

router = Router(name="main")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Добро пожаловать! Нажмите кнопку ниже, чтобы открыть личный кабинет.",
        reply_markup=get_main_keyboard(MINI_APP_URL),
    )
