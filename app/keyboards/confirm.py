from telegram import ReplyKeyboardMarkup


def confirm_menu():

    keyboard = [
        ["✅ Подтвердить"],
        ["❌ Отменить"],
        ["⬅️ Назад"],
    ]

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
    )
