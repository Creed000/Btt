from telegram import KeyboardButton, ReplyKeyboardMarkup

from app.services.access_control import is_platform_admin


def main_menu(
    role: str | None = None,
    telegram_id: int | None = None,
    has_salon: bool | None = None,
    has_master: bool | None = None,
) -> ReplyKeyboardMarkup:
    keyboard = [
        [
            KeyboardButton("📅 Записаться"),
            KeyboardButton("🔍 Найти мастера"),
        ],
        [
            KeyboardButton("👤 Личный кабинет"),
            KeyboardButton(
                "💼 Кабинет мастера"
                if has_master
                else "💼 Стать мастером"
            ),
        ],
        [
            KeyboardButton("ℹ️ Помощь"),
            KeyboardButton("⚙️ Настройки"),
        ],
    ]

    owns_salon = (
        has_salon
        if has_salon is not None
        else role == "owner"
    )

    if owns_salon:
        keyboard.append(
            [KeyboardButton("🏢 Кабинет салона")]
        )
    else:
        keyboard.append(
            [KeyboardButton("🏢 Создать салон")]
        )

    # Если Telegram ID передан, источник прав — Railway.
    if telegram_id is not None:
        has_admin_button = is_platform_admin(
            telegram_id
        )
    else:
        has_admin_button = role == "admin"

    if has_admin_button:
        keyboard.append(
            [KeyboardButton("👑 Админ-панель")]
        )

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите действие",
    )
