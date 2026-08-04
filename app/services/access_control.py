from app.config.settings import settings
from app.models.user import User


def is_platform_owner(
    telegram_id: int,
) -> bool:
    return (
        settings.OWNER_TELEGRAM_ID is not None
        and telegram_id == settings.OWNER_TELEGRAM_ID
    )


def is_platform_admin(
    telegram_id: int,
) -> bool:
    return (
        is_platform_owner(telegram_id)
        or telegram_id in settings.admin_telegram_ids
    )


def can_manage_platform(
    user: User | None,
) -> bool:
    if user is None:
        return False

    return (
        user.is_active
        and is_platform_admin(user.telegram_id)
    )


def can_manage_admins(
    user: User | None,
) -> bool:
    if user is None:
        return False

    return (
        user.is_active
        and is_platform_owner(user.telegram_id)
    )


def can_manage_salon(
    user: User | None,
    salon_owner_id: int,
) -> bool:
    if user is None or not user.is_active:
        return False

    return (
        user.id == salon_owner_id
        or is_platform_admin(user.telegram_id)
    )
