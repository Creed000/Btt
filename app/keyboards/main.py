from telegram import KeyboardButton, ReplyKeyboardMarkup

from app.services.access_control import (
    is_platform_admin,
)


def main_menu(
    role: str | None = None,
    telegram_id: int | None = None,
    has_salon: bool | None = None,
    has_master: bool | None = None,
) -> ReplyKeyboardMarkup:
    """
    Главное меню пользователя.

    role определяет бизнес-роль пользователя
    (client/master/owner).

    Системный admin-доступ определяется Telegram ID
    из Railway settings и не зависит от role.
    """

    if has_master is None:
        has_master = (
            role == "master"
        )

    if has_salon is None:
        has_salon = (
            role == "owner"
        )

    keyboard = [
        [
            KeyboardButton("📅 Записаться"),
            KeyboardButton("🔍 Найти мастера"),
        ],
        [
            KeyboardButton(
                "💼 Кабинет мастера"
                if has_master
                else "💼 Стать мастером"
            ),
            KeyboardButton(
                "👤 Личный кабинет"
            ),
        ],
        [
            KeyboardButton("ℹ️ Помощь"),
            KeyboardButton("⚙️ Настройки"),
        ],
    ]

    if has_salon:
        keyboard.append(
            [
                KeyboardButton(
                    "🏢 Кабинет салона"
                )
            ]
        )

        keyboard.append(
            [
                KeyboardButton(
                    "💳 Тариф и подписка"
                )
            ]
        )
    else:
        keyboard.append(
            [
                KeyboardButton(
                    "🏢 Создать салон"
                )
            ]
        )

    # Если Telegram ID известен —
    # НИКОГДА не доверяем старому role="admin" из БД.
    if telegram_id is not None:
        has_admin_button = (
            is_platform_admin(
                telegram_id
            )
        )
    else:
        # Fallback нужен только для старых внутренних вызовов,
        # где Telegram ID ещё не передаётся.
        has_admin_button = (
            role == "admin"
        )

    if has_admin_button:
        keyboard.append(
            [
                KeyboardButton(
                    "👑 Админ-панель"
                )
            ]
        )

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите действие",
    )
