from telegram import KeyboardButton, ReplyKeyboardMarkup

from app.repositories.master_repository import get_all_masters


def master_menu():

    keyboard = []

    masters = get_all_masters()

    for master in masters:

        name = master.user.first_name

        keyboard.append(
            [KeyboardButton(f"👤 {name} ⭐{master.rating}")]
        )

    keyboard.append(
        [KeyboardButton("⬅️ Назад")]
    )

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
    )
