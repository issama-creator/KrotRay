from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo


def get_main_keyboard(mini_app_url: str, api_url: str) -> InlineKeyboardMarkup:
    """Inline-кнопка: только так Telegram передаёт initData в Mini App."""
    sep = "&" if "?" in mini_app_url else "?"
    url = f"{mini_app_url}{sep}api={api_url}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Личный кабинет",
                    web_app=WebAppInfo(url=url),
                )
            ]
        ]
    )
