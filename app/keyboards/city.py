from telegram import ReplyKeyboardMarkup


def city_menu():

    keyboard = [

        ["🏙 Бишкек"],

        ["🏙 Ош"],

        ["🏙 Джалал-Абад"],

        ["⬅️ Назад"]

    ]

    return ReplyKeyboardMarkup(

        keyboard,

        resize_keyboard=True,

    )
