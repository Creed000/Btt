from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.master import Master
from app.models.salon import Salon
from app.services.subscription_access import (
    salon_has_active_access,
)


def disable_salon_master_bookings(
    db: Session,
    salon_id: int,
) -> int:
    """
    Выключает приём записей у всех мастеров салона.

    Возвращает количество обновлённых профилей.
    """
    result = db.execute(
        update(Master)
        .where(
            Master.salon_id == salon_id,
            Master.booking_enabled.is_(True),
        )
        .values(
            booking_enabled=False
        )
    )

    return int(
        result.rowcount or 0
    )


def sync_salon_booking_access(
    db: Session,
    salon: Salon,
) -> tuple[bool, str, int]:
    """
    Проверяет доступ салона.

    Если подписка, пробный период или сам салон неактивны,
    выключает приём записей у всех мастеров.

    Возвращает:
    allowed, reason, disabled_masters_count
    """
    allowed, reason = salon_has_active_access(
        salon
    )

    disabled_count = 0

    if not allowed:
        disabled_count = disable_salon_master_bookings(
            db,
            salon.id,
        )

    return (
        allowed,
        reason,
        disabled_count,
    )
