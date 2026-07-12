from telegram import ReplyKeyboardMarkup


def category_menu():

    keyboard = [
        ["💇 Волосы"],
        ["💅 Маникюр"],
        ["👁 Ресницы"],
        ["💆 Массаж"],
        ["⬅️ Назад"],
    ]

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        is_persistent=True,
    )
