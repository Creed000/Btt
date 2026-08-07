import logging

from sqlalchemy import select, update

from app.database.session import SessionLocal
from app.models.master import Master
from app.models.salon import Salon
from app.services.timezone import local_naive_now


logger = logging.getLogger(__name__)


def _salon_has_access(
    salon: Salon,
) -> bool:
    if not salon.is_active:
        return False

    now = local_naive_now()

    if salon.subscription_status == "trial":
        return (
            salon.trial_ends_at is not None
            and salon.trial_ends_at > now
        )

    if salon.subscription_status == "active":
        return (
            salon.subscription_ends_at is not None
            and salon.subscription_ends_at > now
        )

    return False


def maintain_salon_subscriptions() -> dict[str, int]:
    """
    Проверяет ВСЕ салоны.

    Если trial/подписка больше не дают доступ,
    автоматически выключает booking_enabled
    у мастеров этого салона.

    Возвращает статистику для логов/health.
    """
    db = SessionLocal()

    stats = {
        "salons_checked": 0,
        "salons_without_access": 0,
        "masters_disabled": 0,
    }

    try:
        salons = list(
            db.scalars(
                select(Salon)
            ).all()
        )

        stats["salons_checked"] = len(
            salons
        )

        for salon in salons:
            if _salon_has_access(salon):
                continue

            stats[
                "salons_without_access"
            ] += 1

            result = db.execute(
                update(Master)
                .where(
                    Master.salon_id == salon.id,
                    Master.booking_enabled.is_(True),
                )
                .values(
                    booking_enabled=False
                )
            )

            if result.rowcount:
                stats[
                    "masters_disabled"
                ] += result.rowcount

        db.commit()

        if stats["masters_disabled"]:
            logger.warning(
                "Subscription maintenance: "
                "checked=%s no_access=%s "
                "masters_disabled=%s",
                stats["salons_checked"],
                stats["salons_without_access"],
                stats["masters_disabled"],
            )
        else:
            logger.info(
                "Subscription maintenance: "
                "checked=%s no_access=%s",
                stats["salons_checked"],
                stats["salons_without_access"],
            )

        return stats

    except Exception:
        db.rollback()
        logger.exception(
            "Ошибка проверки подписок салонов."
        )
        raise

    finally:
        db.close()
