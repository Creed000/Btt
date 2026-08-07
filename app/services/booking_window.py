from datetime import date, timedelta

from app.services.timezone import local_today


BOOKING_WINDOW_DAYS = 14


def booking_window_dates() -> list[date]:
    today = local_today()

    return [
        today + timedelta(days=offset)
        for offset in range(BOOKING_WINDOW_DAYS)
    ]


def is_date_in_booking_window(
    booking_date: date,
) -> bool:
    today = local_today()
    last_date = today + timedelta(
        days=BOOKING_WINDOW_DAYS - 1
    )

    return today <= booking_date <= last_date
