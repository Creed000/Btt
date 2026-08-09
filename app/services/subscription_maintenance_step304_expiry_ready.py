import logging

from sqlalchemy import or_, select, update

from app.database.session import SessionLocal
from app.models.master import Master
from app.models.salon import Salon
from app.services.timezone import local_naive_now


logger = logging.getLogger(__name__)


def _expired_salons_query(now):
    return (
        select(Salon)
        .where(
            Salon.is_active.is_(True),
            or_(
                (
                    (Salon.subscription_status == "trial")
                    & (Salon.trial_ends_at.is_not(None))
                    & (Salon.trial_ends_at <= now)
                ),
                (
                    (Salon.subscription_status == "active")
                    & (Salon.subscription_ends_at.is_not(None))
                    & (Salon.subscription_ends_at <= now)
                ),
            ),
        )
        .order_by(Salon.id)
        .with_for_update(skip_locked=True)
    )


def maintain_salon_subscriptions() -> int:
    """
    Переводит завершившиеся trial/active подписки в expired.

    Важно:
    - Salon.is_active остаётся True, чтобы владелец мог
      открыть кабинет и продлить тариф.
    - booking_enabled выключается только у мастеров
      просроченных салонов.
    - Повторный запуск идемпотентен: status='expired'
      больше не попадает в выборку.

    Возвращает количество салонов, переведённых
    в expired за этот запуск.
    """
    db = SessionLocal()

    try:
        now = local_naive_now()

        salons = list(
            db.scalars(
                _expired_salons_query(now)
            ).all()
        )

        if not salons:
            return 0

        salon_ids = [
            salon.id
            for salon in salons
        ]

        for salon in salons:
            salon.subscription_status = "expired"
            salon.updated_at = now
            db.add(salon)

        db.execute(
            update(Master)
            .where(
                Master.salon_id.in_(salon_ids),
                Master.booking_enabled.is_(True),
            )
            .values(
                booking_enabled=False
            )
        )

        db.commit()

        logger.info(
            "Истекло подписок/пробных периодов: %s; "
            "новые записи мастеров выключены.",
            len(salon_ids),
        )

        return len(salon_ids)

    except Exception:
        db.rollback()

        logger.exception(
            "Ошибка обслуживания подписок салонов."
        )
        raise

    finally:
        db.close()
