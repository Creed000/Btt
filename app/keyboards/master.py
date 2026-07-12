from telegram import ReplyKeyboardMarkup


def master_menu():

    keyboard = [

        ["👩 Айжан ⭐4.9"],

        ["👩 Алина ⭐5.0"],

        ["👨 Азамат ⭐4.8"],

        ["⬅️ Назад"]

    ]

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
    )
