from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload, Session

from app.models.category import Category
from app.models.city import City
from app.models.master import Master
from app.models.service import Service
from app.models.user import User
from app.services.subscription_access import (
    salon_has_active_access,
)


def get_available_master_services(
    db: Session,
    master_id: int,
    city_name: str,
    category_name: str,
) -> tuple[Master, list[Service]]:
    """
    Проверяет мастера и возвращает только услуги выбранной категории.

    Выбрасывает ValueError, если мастер больше недоступен,
    находится в другом городе, не относится к категории
    или подписка его салона закончилась.
    """
    master = db.scalar(
        select(Master)
        .options(
            joinedload(Master.user),
            joinedload(Master.city),
            joinedload(Master.salon),
            selectinload(Master.services).joinedload(
                Service.category
            ),
        )
        .where(
            Master.id == master_id,
            Master.booking_enabled.is_(True),
            Master.is_verified.is_(True),
        )
    )

    if master is None:
        raise ValueError(
            "Мастер больше не принимает записи."
        )

    if master.user is None or not master.user.is_active:
        raise ValueError(
            "Аккаунт мастера временно недоступен."
        )

    if (
        master.city is None
        or not master.city.is_active
        or master.city.name != city_name
    ):
        raise ValueError(
            "Мастер недоступен в выбранном городе."
        )

    if master.salon is not None:
        allowed, reason = salon_has_active_access(
            master.salon
        )

        if not allowed:
            raise ValueError(reason)

    services = list(
        db.scalars(
            select(Service)
            .join(
                Category,
                Category.id == Service.category_id,
            )
            .join(
                Master,
                Master.id == Service.master_id,
            )
            .join(
                User,
                User.id == Master.user_id,
            )
            .join(
                City,
                City.id == Master.city_id,
            )
            .where(
                Service.master_id == master_id,
                Category.name == category_name,
                City.name == city_name,
                City.is_active.is_(True),
                Master.booking_enabled.is_(True),
                Master.is_verified.is_(True),
                User.is_active.is_(True),
            )
            .order_by(
                Service.title.asc()
            )
        ).all()
    )

    if not services:
        raise ValueError(
            "У мастера нет услуг в выбранной категории."
        )

    return master, services
