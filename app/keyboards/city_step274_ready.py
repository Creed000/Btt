from telegram import KeyboardButton, ReplyKeyboardMarkup

from app.database.session import SessionLocal
from app.services.booking_selection import EMPTY_CITY_BUTTON
from app.services.master_catalog import available_masters_query


def city_menu() -> ReplyKeyboardMarkup:
    db = SessionLocal()

    try:
        masters = list(
            db.scalars(
                available_masters_query()
            ).unique().all()
        )

        city_names = sorted(
            {
                master.city.name
                for master in masters
                if master.city is not None
                and master.city.name
            }
        )

        keyboard: list[list[KeyboardButton]] = [
            [KeyboardButton(f"🏙 {city_name}")]
            for city_name in city_names
        ]

        if not keyboard:
            keyboard.append(
                [KeyboardButton(EMPTY_CITY_BUTTON)]
            )

        keyboard.append(
            [KeyboardButton("⬅️ Назад")]
        )

        return ReplyKeyboardMarkup(
            keyboard=keyboard,
            resize_keyboard=True,
            one_time_keyboard=False,
            input_field_placeholder="Выберите город",
        )

    finally:
        db.close()
