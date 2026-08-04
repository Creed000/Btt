from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.database.session import SessionLocal
from app.models.booking import Booking
from app.models.master import Master
from app.models.master_day_off import MasterDayOff
from app.models.master_schedule import MasterSchedule
from app.models.master_time_block import MasterTimeBlock
from app.models.service import Service
from app.models.user import User
from app.services.subscription_access import salon_has_active_access


ACTIVE_BOOKING_STATUSES = {
    "new",
    "confirmed",
}

DEFAULT_WORK_START = time(hour=9, minute=0)
DEFAULT_WORK_END = time(hour=18, minute=0)


def _intervals_overlap(
    first_start: datetime,
    first_end: datetime,
    second_start: datetime,
    second_end: datetime,
) -> bool:
    return first_start < second_end and second_start < first_end


def _validate_master_schedule(
    db,
    master_id: int,
    selected_start: datetime,
    selected_end: datetime,
) -> None:
    booking_date = selected_start.date()

    day_off = db.scalar(
        select(MasterDayOff.id).where(
            MasterDayOff.master_id == master_id,
            MasterDayOff.day_off_date == booking_date,
        )
    )

    if day_off is not None:
        raise ValueError(
            "На выбранную дату у мастера выходной."
        )

    schedule = db.scalar(
        select(MasterSchedule).where(
            MasterSchedule.master_id == master_id,
            MasterSchedule.weekday == booking_date.weekday(),
        )
    )

    if schedule is None:
        work_start = DEFAULT_WORK_START
        work_end = DEFAULT_WORK_END
    else:
        if not schedule.is_working:
            raise ValueError(
                "В выбранный день мастер не работает."
            )

        work_start = schedule.work_start
        work_end = schedule.work_end

    work_start_dt = datetime.combine(
        booking_date,
        work_start,
    )
    work_end_dt = datetime.combine(
        booking_date,
        work_end,
    )

    if (
        selected_start < work_start_dt
        or selected_end > work_end_dt
    ):
        raise ValueError(
            "Выбранное время находится вне рабочего графика мастера."
        )

    time_blocks = list(
        db.scalars(
            select(MasterTimeBlock).where(
                MasterTimeBlock.master_id == master_id,
                MasterTimeBlock.block_date == booking_date,
            )
        ).all()
    )

    for block in time_blocks:
        block_start = datetime.combine(
            block.block_date,
            block.start_time,
        )
        block_end = datetime.combine(
            block.block_date,
            block.end_time,
        )

        if _intervals_overlap(
            selected_start,
            selected_end,
            block_start,
            block_end,
        ):
            raise ValueError(
                "Выбранное время временно заблокировано мастером."
            )


def create_booking(
    telegram_id: int,
    master_id: int,
    service_id: int,
    booking_date: date,
    booking_time: time,
) -> Booking:
    db = SessionLocal()

    try:
        user = db.scalar(
            select(User).where(
                User.telegram_id == telegram_id
            )
        )

        if user is None:
            raise ValueError(
                "Пользователь не зарегистрирован. Отправьте /start."
            )

        if not user.is_active:
            raise ValueError(
                "Ваш аккаунт временно отключён."
            )

        master = db.scalar(
            select(Master)
            .options(
                joinedload(Master.user),
                joinedload(Master.salon),
            )
            .where(
                Master.id == master_id,
                Master.booking_enabled.is_(True),
            )
        )

        if master is None:
            raise ValueError(
                "Мастер не найден или временно не принимает записи."
            )

        if master.user is None or not master.user.is_active:
            raise ValueError(
                "Аккаунт мастера временно недоступен."
            )

        if not master.is_verified:
            raise ValueError(
                "Профиль мастера ещё не подтверждён администратором."
            )

        if master.salon is not None:
            allowed, reason = salon_has_active_access(
                master.salon
            )

            if not allowed:
                raise ValueError(reason)

        service = db.scalar(
            select(Service).where(
                Service.id == service_id,
                Service.master_id == master_id,
            )
        )

        if service is None:
            raise ValueError(
                "Услуга не найдена или не принадлежит выбранному мастеру."
            )

        selected_start = datetime.combine(
            booking_date,
            booking_time,
        )

        selected_end = selected_start + timedelta(
            minutes=service.duration
        )

        if selected_start <= datetime.now():
            raise ValueError(
                "Нельзя записаться на прошедшую дату или время."
            )

        _validate_master_schedule(
            db,
            master_id,
            selected_start,
            selected_end,
        )

        existing_bookings = list(
            db.scalars(
                select(Booking)
                .options(
                    joinedload(Booking.service)
                )
                .where(
                    Booking.master_id == master_id,
                    Booking.booking_date == booking_date,
                    Booking.status.in_(
                        ACTIVE_BOOKING_STATUSES
                    ),
                )
            ).all()
        )

        for existing in existing_bookings:
            existing_start = datetime.combine(
                existing.booking_date,
                existing.booking_time,
            )

            existing_duration = (
                existing.service.duration
                if existing.service
                else 30
            )

            existing_end = existing_start + timedelta(
                minutes=existing_duration
            )

            if _intervals_overlap(
                selected_start,
                selected_end,
                existing_start,
                existing_end,
            ):
                raise ValueError(
                    "Выбранное время пересекается с другой записью. "
                    "Выберите другой свободный слот."
                )

        booking = Booking(
            client_id=user.id,
            master_id=master_id,
            service_id=service_id,
            booking_date=booking_date,
            booking_time=booking_time,
            status="new",
        )

        db.add(booking)
        db.commit()

        loaded_booking = db.scalar(
            select(Booking)
            .options(
                joinedload(Booking.client),
                joinedload(Booking.master).joinedload(
                    Master.user
                ),
                joinedload(Booking.service),
            )
            .where(Booking.id == booking.id)
        )

        if loaded_booking is None:
            raise RuntimeError(
                "Созданная запись не найдена."
            )

        db.expunge_all()

        return loaded_booking

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()
