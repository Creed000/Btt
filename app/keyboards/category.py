from telegram import KeyboardButton, ReplyKeyboardMarkup

from app.database.session import SessionLocal
from app.services.booking_selection import EMPTY_CATEGORY_BUTTON
from app.services.master_catalog import available_masters_query


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
        masters = list(
            db.scalars(
                available_masters_query(
                    city_name=city_name,
                )
            ).unique().all()
        )

        category_names = sorted(
            {
                service.category.name
                for master in masters
                for service in master.services
                if service.category is not None
                and service.category.name
            }
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
