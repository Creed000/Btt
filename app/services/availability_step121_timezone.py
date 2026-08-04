from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.booking import Booking
from app.models.master_day_off import MasterDayOff
from app.models.master_schedule import MasterSchedule
from app.models.master_time_block import MasterTimeBlock
from app.models.service import Service
from app.services.timezone import local_naive_now


DEFAULT_WORK_START = time(hour=9, minute=0)
DEFAULT_WORK_END = time(hour=18, minute=0)
SLOT_STEP_MINUTES = 30

ACTIVE_BOOKING_STATUSES = {
    "new",
    "confirmed",
}


def _overlaps(
    first_start: datetime,
    first_end: datetime,
    second_start: datetime,
    second_end: datetime,
) -> bool:
    return first_start < second_end and second_start < first_end


def master_has_day_off(
    db: Session,
    master_id: int,
    booking_date: date,
) -> bool:
    day_off = db.scalar(
        select(MasterDayOff.id).where(
            MasterDayOff.master_id == master_id,
            MasterDayOff.day_off_date == booking_date,
        )
    )

    return day_off is not None


def get_master_working_hours(
    db: Session,
    master_id: int,
    booking_date: date,
) -> tuple[time, time] | None:
    if master_has_day_off(
        db,
        master_id,
        booking_date,
    ):
        return None

    weekday = booking_date.weekday()

    schedule = db.scalar(
        select(MasterSchedule).where(
            MasterSchedule.master_id == master_id,
            MasterSchedule.weekday == weekday,
        )
    )

    if schedule is None:
        return DEFAULT_WORK_START, DEFAULT_WORK_END

    if not schedule.is_working:
        return None

    return schedule.work_start, schedule.work_end


def get_master_time_blocks(
    db: Session,
    master_id: int,
    booking_date: date,
) -> list[MasterTimeBlock]:
    return list(
        db.scalars(
            select(MasterTimeBlock)
            .where(
                MasterTimeBlock.master_id == master_id,
                MasterTimeBlock.block_date == booking_date,
            )
            .order_by(MasterTimeBlock.start_time)
        ).all()
    )


def get_available_slots(
    db: Session,
    master_id: int,
    service_id: int,
    booking_date: date,
) -> list[time]:
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

    working_hours = get_master_working_hours(
        db,
        master_id,
        booking_date,
    )

    if working_hours is None:
        return []

    work_start, work_end = working_hours

    if work_end <= work_start:
        raise ValueError(
            "У мастера неверно настроено рабочее время."
        )

    bookings = list(
        db.scalars(
            select(Booking)
            .options(joinedload(Booking.service))
            .where(
                Booking.master_id == master_id,
                Booking.booking_date == booking_date,
                Booking.status.in_(ACTIVE_BOOKING_STATUSES),
            )
            .order_by(Booking.booking_time)
        ).all()
    )

    time_blocks = get_master_time_blocks(
        db,
        master_id,
        booking_date,
    )

    day_start = datetime.combine(
        booking_date,
        work_start,
    )

    day_end = datetime.combine(
        booking_date,
        work_end,
    )

    now = local_naive_now()
    current_start = day_start

    service_duration = timedelta(
        minutes=service.duration
    )

    step = timedelta(
        minutes=SLOT_STEP_MINUTES
    )

    available_slots: list[time] = []

    while current_start + service_duration <= day_end:
        current_end = current_start + service_duration

        if current_start <= now:
            current_start += step
            continue

        slot_is_busy = False

        for booking in bookings:
            existing_start = datetime.combine(
                booking.booking_date,
                booking.booking_time,
            )

            existing_duration = (
                booking.service.duration
                if booking.service
                else SLOT_STEP_MINUTES
            )

            existing_end = existing_start + timedelta(
                minutes=existing_duration
            )

            if _overlaps(
                current_start,
                current_end,
                existing_start,
                existing_end,
            ):
                slot_is_busy = True
                break

        if slot_is_busy:
            current_start += step
            continue

        for block in time_blocks:
            block_start = datetime.combine(
                block.block_date,
                block.start_time,
            )

            block_end = datetime.combine(
                block.block_date,
                block.end_time,
            )

            if _overlaps(
                current_start,
                current_end,
                block_start,
                block_end,
            ):
                slot_is_busy = True
                break

        if not slot_is_busy:
            available_slots.append(
                current_start.time()
            )

        current_start += step

    return available_slots
