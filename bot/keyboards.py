from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo


def get_main_keyboard(mini_app_url: str, api_url: str) -> ReplyKeyboardMarkup:
    sep = "&" if "?" in mini_app_url else "?"
    url = f"{mini_app_url}{sep}api={api_url}"
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="Личный кабинет",
                    web_app=WebAppInfo(url=url),
                )
            ]
        ],
        resize_keyboard=True,
    )
