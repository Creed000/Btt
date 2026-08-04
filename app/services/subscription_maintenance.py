import logging

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.database.session import SessionLocal
from app.models.salon import Salon
from app.services.salon_booking_access import (
    sync_salon_booking_access,
)


logger = logging.getLogger(__name__)


def process_expired_salon_access() -> dict[str, int]:
    """
    Проверяет все активные салоны и синхронизирует доступ к записи.

    Если пробный период или подписка закончились:
    - статус подписки обновляется через salon_has_active_access();
    - приём записей выключается у всех мастеров салона.

    Возвращает статистику выполнения.
    """
    db = SessionLocal()

    checked_salons = 0
    expired_salons = 0
    disabled_masters = 0

    try:
        salons = list(
            db.scalars(
                select(Salon)
                .options(
                    joinedload(Salon.owner)
                )
                .where(
                    Salon.is_active.is_(True)
                )
                .order_by(Salon.id)
            ).unique().all()
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
                expired_salons += 1
                disabled_masters += disabled_count

                logger.info(
                    "Доступ салона #%s отключён: %s. "
                    "Отключено мастеров: %s",
                    salon.id,
                    reason,
                    disabled_count,
                )

        db.commit()

        return {
            "checked_salons": checked_salons,
            "expired_salons": expired_salons,
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
