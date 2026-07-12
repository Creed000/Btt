from telegram import ReplyKeyboardMarkup


def time_menu():

    keyboard = [
        ["🕘 09:00", "🕙 10:00"],
        ["🕚 11:00", "🕛 12:00"],
        ["🕐 13:00", "🕑 14:00"],
        ["🕒 15:00", "🕓 16:00"],
        ["⬅️ Назад"],
    ]

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
    )
