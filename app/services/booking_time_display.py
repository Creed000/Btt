from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from app.config.settings import settings
from app.models.user import User
from app.services.user_timezone import (
    format_datetime_for_user,
    get_user_timezone,
)


def combine_booking_datetime(
    booking_date: date,
    booking_time: time,
) -> datetime:
    return datetime.combine(
        booking_date,
        booking_time,
    )


def format_booking_time_for_user(
    booking_date: date,
    booking_time: time,
    user: User | None,
) -> str:
    """
    Показывает время записи без двусмысленности.

    Если часовой пояс пользователя совпадает с APP_TIMEZONE,
    возвращается одна строка.

    Если отличается, отображаются:
    - время салона/приложения;
    - локальное время пользователя.
    """
    booking_datetime = combine_booking_datetime(
        booking_date,
        booking_time,
    )

    app_timezone = ZoneInfo(
        settings.APP_TIMEZONE
    )
    user_timezone = get_user_timezone(
        user
    )

    app_time_text = booking_datetime.strftime(
        "%d.%m.%Y %H:%M"
    )

    if user_timezone.key == app_timezone.key:
        return (
            f"{app_time_text} "
            f"({settings.APP_TIMEZONE})"
        )

    user_time_text = format_datetime_for_user(
        booking_datetime,
        user,
        pattern="%d.%m.%Y %H:%M",
    )

    return (
        f"Время салона: {app_time_text} "
        f"({settings.APP_TIMEZONE})\n"
        f"Ваше время: {user_time_text} "
        f"({user_timezone.key})"
    )
