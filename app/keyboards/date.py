from telegram import ReplyKeyboardMarkup


def date_menu():

    keyboard = [
        ["📅 Сегодня"],
        ["📅 Завтра"],
        ["📅 Послезавтра"],
        ["⬅️ Назад"],
    ]

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
    )
