from telegram import KeyboardButton, ReplyKeyboardMarkup

from app.database.session import SessionLocal
from app.repositories.master_repository import MasterRepository


def master_menu() -> ReplyKeyboardMarkup:
    db = SessionLocal()
    try:
        masters = [
            master
            for master in MasterRepository.get_all(db)
            if master.booking_enabled
        ]

        keyboard: list[list[KeyboardButton]] = []

        for master in masters:
            name = master.user.first_name or "Без имени"
            keyboard.append(
                [
                    KeyboardButton(
                        f"👤 {name} · #{master.id} ⭐ {master.rating:.1f}"
                    )
                ]
            )

        if not keyboard:
            keyboard.append([KeyboardButton("Мастеров пока нет")])

        keyboard.append([KeyboardButton("⬅️ Назад")])

        return ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
            one_time_keyboard=False,
        )
    finally:
        db.close()
