from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.category import Category
from app.models.master import Master
from app.models.service import Service
from app.services.master_catalog import master_is_available


def get_available_master_services(
    db: Session,
    master_id: int,
    city_name: str,
    category_name: str,
) -> tuple[Master, list[Service]]:
    master = master_is_available(
        db,
        master_id,
        city_name=city_name,
        category_name=category_name,
    )

    if master is None:
        raise ValueError(
            "Этот мастер больше недоступен для записи. "
            "Выберите другого мастера."
        )

    services = list(
        db.scalars(
            select(Service)
            .options(
                joinedload(Service.category)
            )
            .join(
                Category,
                Category.id == Service.category_id,
            )
            .where(
                Service.master_id == master.id,
                Category.name == category_name,
                Service.duration > 0,
                Service.price >= 0,
            )
            .order_by(
                Service.title,
                Service.id,
            )
        ).unique().all()
    )

    if not services:
        raise ValueError(
            "У выбранного мастера больше нет "
            "доступных услуг в этой категории."
        )

    return master, services


def resolve_selected_service(
    db: Session,
    service_id: int,
    master_id: int,
    city_name: str,
    category_name: str,
) -> Service:
    master = master_is_available(
        db,
        master_id,
        city_name=city_name,
        category_name=category_name,
    )

    if master is None:
        raise ValueError(
            "Этот мастер больше недоступен для записи. "
            "Начните выбор заново."
        )

    service = db.scalar(
        select(Service)
        .options(
            joinedload(Service.category)
        )
        .join(
            Category,
            Category.id == Service.category_id,
        )
        .where(
            Service.id == service_id,
            Service.master_id == master.id,
            Category.name == category_name,
            Service.duration > 0,
            Service.price >= 0,
        )
    )

    if service is None:
        raise ValueError(
            "Эта услуга больше недоступна у выбранного мастера. "
            "Выберите услугу заново."
        )

    return service
