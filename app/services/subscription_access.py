from app.models.salon import Salon
from app.services.timezone import local_naive_now


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
    now = local_naive_now()

    if salon.subscription_status == "trial":
        if (
            salon.trial_ends_at is None
            or salon.trial_ends_at <= now
        ):
            salon.subscription_status = "expired"

    elif salon.subscription_status == "active":
        if (
            salon.subscription_ends_at is None
            or salon.subscription_ends_at <= now
        ):
            salon.subscription_status = "expired"


def salon_has_active_access(
    salon: Salon,
) -> tuple[bool, str]:
    original_status = salon.subscription_status

    refresh_subscription_status(
        salon
    )

    if not salon.is_active:
        return (
            False,
            "Салон временно отключён.",
        )

    if salon.subscription_status == "expired":
        if original_status == "trial":
            return (
                False,
                "Пробный период завершён или не настроен.",
            )

        if original_status == "active":
            return (
                False,
                "Срок подписки завершён или не настроен.",
            )

    if salon.subscription_status not in ACTIVE_SUBSCRIPTION_STATUSES:
        return (
            False,
            (
                "Подписка салона неактивна. "
                "Откройте «💳 Тариф и подписка»."
            ),
        )

    return True, ""


def require_active_salon_access(
    salon: Salon,
) -> None:
    allowed, reason = salon_has_active_access(
        salon
    )

    if not allowed:
        raise ValueError(reason)
