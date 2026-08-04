import logging

from sqlalchemy import select

from app.database.session import SessionLocal
from app.models.salon import Salon
from app.services.salon_booking_access import (
    sync_salon_booking_access,
)


logger = logging.getLogger(__name__)


def process_expired_salon_access() -> dict[str, int]:
    """
    Проверяет все салоны и синхронизирует доступ к записи.

    Обрабатываются:
    - активные подписки;
    - пробные периоды;
    - просроченные подписки;
    - отменённые подписки;
    - отключённые салоны.

    Если доступ недействителен, приём записей выключается
    у всех мастеров соответствующего салона.
    """
    db = SessionLocal()

    checked_salons = 0
    blocked_salons = 0
    disabled_masters = 0

    try:
        salons = list(
            db.scalars(
                select(Salon)
                .order_by(Salon.id)
            ).all()
        )

        for salon in salons:
            checked_salons += 1

            allowed, reason, disabled_count = (
                sync_salon_booking_access(
                    db,
                    salon,
                )
            )

            if not allowed:
                blocked_salons += 1
                disabled_masters += disabled_count

                logger.info(
                    "Доступ салона #%s ограничен: %s. "
                    "Отключено мастеров: %s",
                    salon.id,
                    reason,
                    disabled_count,
                )

        db.commit()

        return {
            "checked_salons": checked_salons,
            "expired_salons": blocked_salons,
            "disabled_masters": disabled_masters,
        }

    except Exception:
        db.rollback()
        logger.exception(
            "Ошибка автоматической проверки подписок салонов"
        )
        raise

    finally:
        db.close()
