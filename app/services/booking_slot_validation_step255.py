from datetime import date, time

from sqlalchemy.orm import Session

from app.services.availability import get_available_slots
from app.services.booking_window import (
    BOOKING_WINDOW_DAYS,
    is_date_in_booking_window,
)


def validate_selected_booking_slot(
    db: Session,
    master_id: int,
    service_id: int,
    booking_date: date,
    booking_time: time,
) -> None:
    if not is_date_in_booking_window(
        booking_date
    ):
        raise ValueError(
            "Дата недоступна для записи. "
            f"Можно выбрать дату только в ближайшие "
            f"{BOOKING_WINDOW_DAYS} дней."
        )

    available_slots = get_available_slots(
        db=db,
        master_id=master_id,
        service_id=service_id,
        booking_date=booking_date,
    )

    if booking_time not in available_slots:
        raise ValueError(
            "Это время уже занято или больше недоступно. "
            "Выберите другой свободный слот."
        )
