from telegram import KeyboardButton, ReplyKeyboardMarkup

from app.services.booking_window import booking_window_dates


WEEKDAY_NAMES = {
    0: "Пн",
    1: "Вт",
    2: "Ср",
    3: "Чт",
    4: "Пт",
    5: "Сб",
    6: "Вс",
}


def date_menu() -> ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]] = []

    dates = booking_window_dates()

    for offset, selected_date in enumerate(dates):
        if offset == 0:
            label = "Сегодня"
        elif offset == 1:
            label = "Завтра"
        else:
            label = WEEKDAY_NAMES[
                selected_date.weekday()
            ]

        button_text = (
            f"📅 {label}, "
            f"{selected_date.strftime('%d.%m')} "
            f"· {selected_date.isoformat()}"
        )

        keyboard.append(
            [KeyboardButton(button_text)]
        )

    keyboard.append(
        [KeyboardButton("⬅️ Назад")]
    )

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите дату",
    )
