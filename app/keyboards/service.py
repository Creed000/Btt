from telegram import KeyboardButton, ReplyKeyboardMarkup

from app.models.service import Service


def service_menu(
    services: list[Service],
) -> ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]] = []

    for service in services:
        keyboard.append(
            [
                KeyboardButton(
                    f"💼 {service.title} · #{service.id} "
                    f"· {service.duration} мин · {service.price}"
                )
            ]
        )

    if not keyboard:
        keyboard.append(
            [KeyboardButton("Услуг пока нет")]
        )

    keyboard.append(
        [KeyboardButton("⬅️ Назад")]
    )

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите услугу",
    )
