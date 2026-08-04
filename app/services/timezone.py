import os
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_TIMEZONE = "Asia/Bishkek"


def get_app_timezone() -> ZoneInfo:
    timezone_name = os.getenv(
        "APP_TIMEZONE",
        DEFAULT_TIMEZONE,
    )

    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo(DEFAULT_TIMEZONE)


APP_TIMEZONE = get_app_timezone()


def local_now() -> datetime:
    """
    Возвращает текущее локальное время приложения.
    """
    return datetime.now(APP_TIMEZONE)


def local_naive_now() -> datetime:
    """
    Возвращает локальное время без timezone-информации.

    Используется для совместимости с текущими колонками PostgreSQL
    типа TIMESTAMP WITHOUT TIME ZONE.
    """
    return local_now().replace(tzinfo=None)


def to_local_naive(
    value: datetime,
) -> datetime:
    """
    Приводит datetime к локальному времени без timezone-информации.
    """
    if value.tzinfo is None:
        return value

    return value.astimezone(
        APP_TIMEZONE
    ).replace(tzinfo=None)
