from datetime import timedelta

from telegram import KeyboardButton, ReplyKeyboardMarkup

from app.services.timezone import local_today


WEEKDAY_NAMES = {
    0: "Пн",
    1: "Вт",
    2: "Ср",
    3: "Чт",
    4: "Пт",
    5: "Сб",
    6: "Вс",
}


def date_menu(
    days_count: int = 14,
) -> ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]] = []

    today = local_today()

    for offset in range(days_count):
        selected_date = today + timedelta(
            days=offset
        )

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
