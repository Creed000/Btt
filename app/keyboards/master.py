from telegram import KeyboardButton, ReplyKeyboardMarkup

from app.database.session import SessionLocal
from app.services.master_catalog import (
    available_masters_query,
)


def master_menu(
    city_name: str | None = None,
    category_name: str | None = None,
) -> ReplyKeyboardMarkup:
    db = SessionLocal()

    try:
        masters = list(
            db.scalars(
                available_masters_query(
                    city_name=city_name,
                    category_name=category_name,
                )
            ).unique().all()
        )

        keyboard: list[list[KeyboardButton]] = []

        for master in masters:
            name = (
                master.user.first_name
                if master.user
                and master.user.first_name
                else "Без имени"
            )

            city_name_value = (
                master.city.name
                if master.city
                else "Город не указан"
            )

            place_name = (
                master.salon.name
                if master.salon
                else "Самостоятельный мастер"
            )

            keyboard.append(
                [
                    KeyboardButton(
                        f"👤 {name} · #{master.id} "
                        f"⭐ {master.rating:.1f} · "
                        f"{city_name_value} · "
                        f"{place_name}"
                    )
                ]
            )

        if not keyboard:
            keyboard.append(
                [
                    KeyboardButton(
                        "Подходящих мастеров нет"
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
            input_field_placeholder="Выберите мастера",
        )

    finally:
        db.close()
