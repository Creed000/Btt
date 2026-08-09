from telegram import KeyboardButton, ReplyKeyboardMarkup

from app.database.session import SessionLocal
from app.services.booking_selection import EMPTY_CATEGORY_BUTTON
from app.services.master_catalog import available_category_names


CATEGORY_ICONS = {
    "Волосы": "💇",
    "Маникюр": "💅",
    "Ресницы": "👁",
    "Массаж": "💆",
}


def category_menu(
    city_name: str | None = None,
) -> ReplyKeyboardMarkup:
    db = SessionLocal()

    try:
        category_names = available_category_names(
            db,
            city_name=city_name,
        )

        keyboard: list[list[KeyboardButton]] = []

        for category_name in category_names:
            icon = CATEGORY_ICONS.get(
                category_name,
                "✨",
            )

            keyboard.append(
                [
                    KeyboardButton(
                        f"{icon} {category_name}"
                    )
                ]
            )

        if not keyboard:
            keyboard.append(
                [
                    KeyboardButton(
                        EMPTY_CATEGORY_BUTTON
                    )
                ]
            )

        keyboard.append(
            [KeyboardButton("⬅️ Назад")]
        )

        return ReplyKeyboardMarkup(
            keyboard=keyboard,
            resize_keyboard=True,
            one_time_keyboard=False,
            input_field_placeholder="Выберите категорию",
        )

    finally:
        db.close()
