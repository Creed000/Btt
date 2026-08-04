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


def _validate_master_access(
    master: Master,
    city_name: str,
) -> None:
    if master.user is None or not master.user.is_active:
        raise ValueError(
            "Аккаунт мастера временно недоступен."
        )

    if not master.is_verified:
        raise ValueError(
            "Профиль мастера больше не подтверждён."
        )

    if not master.booking_enabled:
        raise ValueError(
            "Мастер больше не принимает записи."
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


def get_available_master_services(
    db: Session,
    master_id: int,
    city_name: str,
    category_name: str,
) -> tuple[Master, list[Service]]:
    """
    Проверяет мастера и возвращает только услуги выбранной категории.
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
            Master.id == master_id
        )
    )

    if master is None:
        raise ValueError(
            "Мастер не найден."
        )

    _validate_master_access(
        master,
        city_name,
    )

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


def resolve_selected_service(
    db: Session,
    service_id: int,
    master_id: int,
    city_name: str,
    category_name: str,
) -> Service:
    """
    Повторно проверяет выбранную услугу перед открытием календаря.

    Защищает от старой или вручную отправленной кнопки.
    """
    service = db.scalar(
        select(Service)
        .options(
            joinedload(Service.category),
            joinedload(Service.master).joinedload(
                Master.user
            ),
            joinedload(Service.master).joinedload(
                Master.city
            ),
            joinedload(Service.master).joinedload(
                Master.salon
            ),
        )
        .where(
            Service.id == service_id,
            Service.master_id == master_id,
        )
    )

    if service is None:
        raise ValueError(
            "Услуга не найдена или не принадлежит выбранному мастеру."
        )

    master = service.master

    if master is None:
        raise ValueError(
            "Профиль мастера не найден."
        )

    _validate_master_access(
        master,
        city_name,
    )

    if (
        service.category is None
        or service.category.name != category_name
    ):
        raise ValueError(
            "Услуга не относится к выбранной категории."
        )

    if service.duration < 15:
        raise ValueError(
            "У услуги указана некорректная длительность."
        )

    if service.price < 0:
        raise ValueError(
            "У услуги указана некорректная цена."
        )

    return service
