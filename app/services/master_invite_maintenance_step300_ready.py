import logging
from datetime import timedelta

from sqlalchemy import update

from app.database.session import SessionLocal
from app.models.master_salon_invite import MasterSalonInvite
from app.services.timezone import local_naive_now


logger = logging.getLogger(__name__)

INVITE_TTL_DAYS = 7


def expire_stale_master_invites() -> int:
    """
    Автоматически закрывает старые pending-приглашения.

    Возвращает количество приглашений,
    переведённых в status='expired'.
    """
    db = SessionLocal()

    try:
        now = local_naive_now()
        cutoff = now - timedelta(
            days=INVITE_TTL_DAYS
        )

        result = db.execute(
            update(MasterSalonInvite)
            .where(
                MasterSalonInvite.status
                == "pending",
                MasterSalonInvite.created_at
                <= cutoff,
            )
            .values(
                status="expired",
                resolved_at=now,
            )
        )

        expired_count = (
            result.rowcount or 0
        )

        db.commit()

        if expired_count:
            logger.info(
                "Просрочено приглашений мастеров: %s",
                expired_count,
            )

        return expired_count

    except Exception:
        db.rollback()
        logger.exception(
            "Ошибка автоматического истечения "
            "приглашений мастеров."
        )
        raise

    finally:
        db.close()
