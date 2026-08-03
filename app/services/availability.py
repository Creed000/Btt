from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.booking import Booking
from app.models.service import Service


WORK_START = time(hour=9, minute=0)
WORK_END = time(hour=18, minute=0)
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

    day_start = datetime.combine(
        booking_date,
        WORK_START,
    )
    day_end = datetime.combine(
        booking_date,
        WORK_END,
    )

    now = datetime.now()
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

        if not slot_is_busy:
            available_slots.append(
                current_start.time()
            )

        current_start += step

    return available_slots
