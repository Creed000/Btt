from app.models.salon import Salon
from app.services.timezone import local_naive_now


ACTIVE_SUBSCRIPTION_STATUSES = {
    "trial",
    "active",
}


def refresh_subscription_status(
    salon: Salon,
) -> bool:
    """
    Проверяет срок подписки прямо по текущему времени.

    Возвращает True, если статус модели был изменён
    в памяти на ``expired``. Сохранение в БД остаётся
    ответственностью вызывающего кода.
    """
    now = local_naive_now()
    changed = False

    if salon.subscription_status == "trial":
        # Trial без даты окончания не должен давать
        # бессрочный бесплатный доступ.
        if (
            salon.trial_ends_at is None
            or salon.trial_ends_at <= now
        ):
            salon.subscription_status = "expired"
            changed = True

    elif salon.subscription_status == "active":
        # Платная подписка без subscription_ends_at
        # также считается некорректной/истёкшей.
        if (
            salon.subscription_ends_at is None
            or salon.subscription_ends_at <= now
        ):
            salon.subscription_status = "expired"
            changed = True

    return changed


def salon_has_active_access(
    salon: Salon,
) -> tuple[bool, str]:
    """
    Мгновенная проверка доступа.

    Не ждёт hourly maintenance: фактическая дата
    окончания проверяется при каждом вызове.
    """
    if not salon.is_active:
        return (
            False,
            "Салон временно отключён.",
        )

    original_status = salon.subscription_status
    refresh_subscription_status(
        salon
    )

    if salon.subscription_status == "expired":
        if original_status == "trial":
            return (
                False,
                (
                    "Пробный период завершён. "
                    "Откройте «💳 Тариф и подписка»."
                ),
            )

        if original_status == "active":
            return (
                False,
                (
                    "Срок подписки завершён. "
                    "Откройте «💳 Тариф и подписка»."
                ),
            )

        return (
            False,
            (
                "Подписка салона истекла. "
                "Откройте «💳 Тариф и подписка»."
            ),
        )

    if (
        salon.subscription_status
        not in ACTIVE_SUBSCRIPTION_STATUSES
    ):
        return (
            False,
            (
                "Подписка салона неактивна. "
                "Откройте «💳 Тариф и подписка»."
            ),
        )

    # Дополнительная защита на случай нестандартного
    # объекта или изменения модели между проверками.
    now = local_naive_now()

    if salon.subscription_status == "trial":
        if salon.trial_ends_at is None:
            return (
                False,
                "У пробного периода отсутствует дата окончания.",
            )

        if salon.trial_ends_at <= now:
            salon.subscription_status = "expired"
            return (
                False,
                "Пробный период завершён.",
            )

    if salon.subscription_status == "active":
        if salon.subscription_ends_at is None:
            return (
                False,
                "У подписки отсутствует дата окончания.",
            )

        if salon.subscription_ends_at <= now:
            salon.subscription_status = "expired"
            return (
                False,
                "Срок подписки завершён.",
            )

    return True, ""


def require_active_salon_access(
    salon: Salon,
) -> None:
    allowed, reason = salon_has_active_access(
        salon
    )

    if not allowed:
        raise ValueError(
            reason
        )
