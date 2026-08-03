from datetime import time

from telegram import KeyboardButton, ReplyKeyboardMarkup


def available_time_menu(
    slots: list[time],
) -> ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]] = []

    row: list[KeyboardButton] = []

    for slot in slots:
        row.append(
            KeyboardButton(
                f"🕒 {slot.strftime('%H:%M')}"
            )
        )

        if len(row) == 2:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    if not keyboard:
        keyboard.append(
            [KeyboardButton("Свободного времени нет")]
        )

    keyboard.append(
        [KeyboardButton("⬅️ Назад")]
    )

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите свободное время",
    )
