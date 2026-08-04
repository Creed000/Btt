from telegram import KeyboardButton, ReplyKeyboardMarkup

from app.services.access_control import is_platform_admin


def main_menu(
    role: str | None = None,
    telegram_id: int | None = None,
    has_salon: bool | None = None,
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

    # Для старых вызовов без has_salon сохраняем совместимость:
    # роль owner означает владельца салона.
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

    # Админ-панель показываем системным администраторам.
    # Реальный доступ дополнительно проверяется внутри обработчиков.
    has_admin_button = (
        role == "admin"
        or (
            telegram_id is not None
            and is_platform_admin(telegram_id)
        )
    )

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
