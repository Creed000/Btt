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


def _has_service():
    return exists(
        select(Service.id).where(
            Service.master_id == Master.id
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
        # Для мастера салона филиал обязателен.
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

    Сохраняет обратную совместимость со старыми
    вызовами city_name/category_name и одновременно
    применяет новые строгие проверки готовности.
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
            # Расписание должно быть явно настроено
            # на все семь дней недели.
            _schedule_rows_count() == 7,
            _has_working_day(),
            or_(
                # Самостоятельный мастер.
                Master.salon_id.is_(None),
                # Мастер салона с реально действующей
                # подпиской прямо в момент SQL-запроса.
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
    """
    Строгий каталог для одного мастера.

    Удобен для финальной проверки старых кнопок
    Telegram непосредственно перед записью.
    """
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
    """
    Обратная совместимость для booking/create_booking.

    Возвращает Master только если он прямо сейчас
    проходит все проверки единого каталога.
    """
    return db.scalars(
        available_master_by_id_query(
            master_id,
            city_name=city_name,
            category_name=category_name,
        )
    ).unique().first()
