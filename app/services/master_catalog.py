from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import joinedload

from app.models.master import Master
from app.models.master_schedule import MasterSchedule
from app.models.salon import Salon
from app.models.service import Service
from app.models.user import User
from app.services.timezone import local_naive_now


def _schedule_rows_subquery():
    return (
        select(
            func.count(
                MasterSchedule.id
            )
        )
        .where(
            MasterSchedule.master_id
            == Master.id
        )
        .correlate(Master)
        .scalar_subquery()
    )


def _has_working_day():
    return (
        select(MasterSchedule.id)
        .where(
            MasterSchedule.master_id
            == Master.id,
            MasterSchedule.is_working.is_(True),
            MasterSchedule.work_start
            < MasterSchedule.work_end,
        )
        .correlate(Master)
        .exists()
    )


def _has_service():
    return (
        select(Service.id)
        .where(
            Service.master_id
            == Master.id
        )
        .correlate(Master)
        .exists()
    )


def _salon_access_condition():
    """
    Мастер салона доступен только если подписка
    фактически действует прямо сейчас.

    Не полагаемся только на subscription_status:
    дата проверяется внутри SQL-запроса.
    """
    now = local_naive_now()

    valid_trial = and_(
        Salon.subscription_status
        == "trial",
        Salon.trial_ends_at.is_not(
            None
        ),
        Salon.trial_ends_at > now,
    )

    valid_paid = and_(
        Salon.subscription_status
        == "active",
        Salon.subscription_ends_at.is_not(
            None
        ),
        Salon.subscription_ends_at > now,
    )

    return and_(
        Salon.is_active.is_(True),
        or_(
            valid_trial,
            valid_paid,
        ),
    )


def available_masters_query():
    """
    Единый source of truth для каталога мастеров.

    Самостоятельный мастер:
      salon_id IS NULL.

    Мастер салона:
      салон активен и trial/подписка ещё не истекли.

    Для обоих вариантов обязательны:
      - активный User;
      - verified;
      - booking_enabled;
      - выбранный город;
      - хотя бы одна услуга;
      - расписание заполнено на все 7 дней;
      - хотя бы один рабочий день.
    """
    return (
        select(Master)
        .join(
            User,
            User.id == Master.user_id,
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
            joinedload(Master.services),
        )
        .where(
            User.is_active.is_(True),
            Master.is_verified.is_(True),
            Master.booking_enabled.is_(True),
            Master.city_id.is_not(None),
            _has_service(),
            _schedule_rows_subquery() == 7,
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


def available_master_by_id_query(
    master_id: int,
):
    """
    Тот же строгий каталог, но для одного мастера.

    Используется перед выбором мастера/услуги,
    чтобы нельзя было обойти каталог старой кнопкой.
    """
    return available_masters_query().where(
        Master.id == master_id
    )
