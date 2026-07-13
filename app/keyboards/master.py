from telegram import KeyboardButton, ReplyKeyboardMarkup
from sqlalchemy.orm import Session

from app.repositories.master_repository import MasterRepository


def master_menu(db: Session):

    keyboard = []

    masters = MasterRepository.get_all(db)

    for master in masters:

        name = master.user.first_name or "Без имени"

        keyboard.append(
            [KeyboardButton(f"👤 {name} ⭐ {master.rating}")]
        )

    keyboard.append(
        [KeyboardButton("⬅️ Назад")]
    )

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
    )
