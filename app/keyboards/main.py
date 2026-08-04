from telegram import KeyboardButton, ReplyKeyboardMarkup

from app.services.access_control import is_platform_admin


def main_menu(
    role: str | None = None,
    telegram_id: int | None = None,
) -> ReplyKeyboardMarkup:
    keyboard = [
        [
            KeyboardButton("📅 Записаться"),
            KeyboardButton("🔍 Найти мастера"),
        ],
        [
            KeyboardButton("👤 Личный кабинет"),
            KeyboardButton("💼 Стать мастером"),
        ],
        [
            KeyboardButton("ℹ️ Помощь"),
            KeyboardButton("⚙️ Настройки"),
        ],
    ]

    # Роль owner означает владельца конкретного салона.
    if role == "owner":
        keyboard.append(
            [KeyboardButton("🏢 Кабинет салона")]
        )
    else:
        keyboard.append(
            [KeyboardButton("🏢 Создать салон")]
        )

    # Админ-панель показываем только ID из настроек Railway.
    if (
        telegram_id is not None
        and is_platform_admin(telegram_id)
    ):
        keyboard.append(
            [KeyboardButton("👑 Админ-панель")]
        )

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите действие",
    )
