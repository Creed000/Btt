from app.config.settings import settings
from app.models.user import User


def is_platform_owner(
    telegram_id: int | None,
) -> bool:
    if telegram_id is None:
        return False

    return (
        settings.OWNER_TELEGRAM_ID is not None
        and telegram_id
        == settings.OWNER_TELEGRAM_ID
    )


def is_platform_admin(
    telegram_id: int | None,
) -> bool:
    if telegram_id is None:
        return False

    return (
        telegram_id
        in settings.all_platform_admin_ids
    )


def can_manage_platform(
    user: User | None,
) -> bool:
    """
    Источник истины для SaaS-прав:
    активный User + Telegram ID из Railway settings.

    Поле user.role НЕ выдаёт системные права.
    """
    if user is None:
        return False

    return (
        bool(user.is_active)
        and is_platform_admin(
            user.telegram_id
        )
    )


def can_manage_admins(
    user: User | None,
) -> bool:
    """
    Управлять системными администраторами
    может только главный OWNER_TELEGRAM_ID.
    """
    if user is None:
        return False

    return (
        bool(user.is_active)
        and is_platform_owner(
            user.telegram_id
        )
    )


def can_manage_salon(
    user: User | None,
    salon_owner_id: int,
) -> bool:
    """
    Салоном может управлять его владелец
    либо активный системный администратор.
    """
    if (
        user is None
        or not user.is_active
    ):
        return False

    return (
        user.id == salon_owner_id
        or is_platform_admin(
            user.telegram_id
        )
    )


def platform_access_label(
    telegram_id: int | None,
) -> str | None:
    """
    Только для интерфейса/диагностики.
    Не заменяет проверку can_manage_platform().
    """
    if is_platform_owner(
        telegram_id
    ):
        return "owner"

    if is_platform_admin(
        telegram_id
    ):
        return "admin"

    return None
