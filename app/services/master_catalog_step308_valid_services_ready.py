from sqlalchemy import Select, and_, exists, func, or_, select
from sqlalchemy.orm import joinedload

from app.models.category import Category
from app.models.city import City
from app.models.master import Master
from app.models.master_schedule import MasterSchedule
from app.models.salon import Salon
from app.models.service import Service
from app.models.user import User
from app.services.timezone import local_naive_now


def _valid_service_condition():
    return and_(
        Service.duration > 0,
        Service.price >= 0,
    )


def _has_service():
    return exists(
        select(Service.id).where(
            Service.master_id == Master.id,
            _valid_service_condition(),
        )
    )


def _schedule_rows_count():
    return (
        select(func.count(MasterSchedule.id))
        .where(
            MasterSchedule.master_id == Master.id
        )
        .correlate(Master)
        .scalar_subquery()
    )


def _has_working_day():
    return exists(
        select(MasterSchedule.id).where(
            MasterSchedule.master_id == Master.id,
            MasterSchedule.is_working.is_(True),
            MasterSchedule.work_start.is_not(None),
            MasterSchedule.work_end.is_not(None),
            MasterSchedule.work_start < MasterSchedule.work_end,
        )
    )


def _salon_access_condition():
    now = local_naive_now()

    valid_trial = and_(
        Salon.subscription_status == "trial",
        Salon.trial_ends_at.is_not(None),
        Salon.trial_ends_at > now,
    )

    valid_paid = and_(
        Salon.subscription_status == "active",
        Salon.subscription_ends_at.is_not(None),
        Salon.subscription_ends_at > now,
    )

    return and_(
        Salon.is_active.is_(True),
        Master.branch_id.is_not(None),
        or_(
            valid_trial,
            valid_paid,
        ),
    )


def available_masters_query(
    *,
    city_name: str | None = None,
    category_name: str | None = None,
) -> Select:
    """
    Единый source of truth каталога мастеров.

    Услуга считается доступной только если:
    duration > 0 и price >= 0.
    """
    query = (
        select(Master)
        .join(
            User,
            User.id == Master.user_id,
        )
        .join(
            City,
            City.id == Master.city_id,
        )
        .outerjoin(
            Salon,
            Salon.id == Master.salon_id,
        )
        .options(
            joinedload(Master.user),
            joinedload(Master.city),
            joinedload(Master.salon),
            joinedload(Master.branch),
            joinedload(Master.services).joinedload(
                Service.category
            ),
        )
        .where(
            User.is_active.is_(True),
            Master.is_verified.is_(True),
            Master.booking_enabled.is_(True),
            Master.city_id.is_not(None),
            City.is_active.is_(True),
            _has_service(),
            _schedule_rows_count() == 7,
            _has_working_day(),
            or_(
                Master.salon_id.is_(None),
                _salon_access_condition(),
            ),
        )
        .order_by(
            Master.rating.desc(),
            Master.id.asc(),
        )
    )

    if city_name:
        query = query.where(
            City.name == city_name
        )

    if category_name:
        query = query.where(
            exists(
                select(Service.id)
                .join(
                    Category,
                    Category.id == Service.category_id,
                )
                .where(
                    Service.master_id == Master.id,
                    Category.name == category_name,
                    _valid_service_condition(),
                )
            )
        )

    return query


def available_master_by_id_query(
    master_id: int,
    *,
    city_name: str | None = None,
    category_name: str | None = None,
) -> Select:
    return available_masters_query(
        city_name=city_name,
        category_name=category_name,
    ).where(
        Master.id == master_id
    )


def master_is_available(
    db,
    master_id: int,
    *,
    city_name: str | None = None,
    category_name: str | None = None,
) -> Master | None:
    return db.scalars(
        available_master_by_id_query(
            master_id,
            city_name=city_name,
            category_name=category_name,
        )
    ).unique().first()


def available_category_names(
    db,
    *,
    city_name: str | None = None,
) -> list[str]:
    """
    Возвращает только категории, где реально есть
    хотя бы одна валидная услуга доступного мастера.

    Не строит меню по всем eager-loaded services.
    """
    masters_subquery = (
        available_masters_query(
            city_name=city_name
        )
        .with_only_columns(
            Master.id
        )
        .order_by(None)
        .subquery()
    )

    return list(
        db.scalars(
            select(Category.name)
            .join(
                Service,
                Service.category_id == Category.id,
            )
            .where(
                Service.master_id.in_(
                    select(
                        masters_subquery.c.id
                    )
                ),
                _valid_service_condition(),
            )
            .distinct()
            .order_by(
                Category.name.asc()
            )
        ).all()
    )
