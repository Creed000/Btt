from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.config.settings import settings
from app.models.user import User


def get_user_timezone(
    user: User | None,
) -> ZoneInfo:
    """
    Возвращает часовой пояс пользователя.

    При отсутствующем или неверном значении используется
    глобальный APP_TIMEZONE приложения.
    """
    timezone_name = (
        user.timezone
        if user is not None and user.timezone
        else settings.APP_TIMEZONE
    )

    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo(settings.APP_TIMEZONE)


def localize_app_datetime_for_user(
    value: datetime,
    user: User | None,
) -> datetime:
    """
    Переводит локальное время приложения в часовой пояс пользователя.

    В базе даты пока хранятся без timezone-информации и считаются
    временем APP_TIMEZONE.
    """
    app_timezone = ZoneInfo(
        settings.APP_TIMEZONE
    )
    user_timezone = get_user_timezone(
        user
    )

    if value.tzinfo is None:
        value = value.replace(
            tzinfo=app_timezone
        )
    else:
        value = value.astimezone(
            app_timezone
        )

    return value.astimezone(
        user_timezone
    )


def format_datetime_for_user(
    value: datetime,
    user: User | None,
    pattern: str = "%d.%m.%Y %H:%M",
) -> str:
    localized = localize_app_datetime_for_user(
        value,
        user,
    )

    return localized.strftime(
        pattern
    )
