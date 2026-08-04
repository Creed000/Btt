from datetime import datetime

from app.models.salon import Salon


ACTIVE_SUBSCRIPTION_STATUSES = {
    "trial",
    "active",
}


def refresh_subscription_status(
    salon: Salon,
) -> None:
    """
    Обновляет статус подписки в памяти модели.

    Сохранение в базу выполняет вызывающий код через db.commit().
    """
    now = datetime.utcnow()

    if (
        salon.subscription_status == "trial"
        and salon.trial_ends_at is not None
        and salon.trial_ends_at <= now
    ):
        salon.subscription_status = "expired"

    if (
        salon.subscription_status == "active"
        and salon.subscription_ends_at is not None
        and salon.subscription_ends_at <= now
    ):
        salon.subscription_status = "expired"


def salon_has_active_access(
    salon: Salon,
) -> tuple[bool, str]:
    refresh_subscription_status(salon)

    if not salon.is_active:
        return (
            False,
            "Салон временно отключён.",
        )

    if salon.subscription_status not in ACTIVE_SUBSCRIPTION_STATUSES:
        return (
            False,
            (
                "Подписка салона неактивна. "
                "Откройте «💳 Тариф и подписка»."
            ),
        )

    now = datetime.utcnow()

    if (
        salon.subscription_status == "trial"
        and salon.trial_ends_at is not None
        and salon.trial_ends_at <= now
    ):
        return (
            False,
            "Пробный период завершён.",
        )

    if (
        salon.subscription_status == "active"
        and salon.subscription_ends_at is not None
        and salon.subscription_ends_at <= now
    ):
        return (
            False,
            "Срок подписки завершён.",
        )

    return True, ""


def require_active_salon_access(
    salon: Salon,
) -> None:
    allowed, reason = salon_has_active_access(salon)

    if not allowed:
        raise ValueError(reason)
