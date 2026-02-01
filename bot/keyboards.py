from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo


def get_main_keyboard(mini_app_url: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="Личный кабинет",
                    web_app=WebAppInfo(url=mini_app_url),
                )
            ]
        ],
        resize_keyboard=True,
    )
