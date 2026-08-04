from datetime import date, time, timedelta

from sqlalchemy.orm import Session

from app.services.availability import get_available_slots
from app.services.timezone import local_today


BOOKING_WINDOW_DAYS = 14


def validate_selected_booking_slot(
    db: Session,
    master_id: int,
    service_id: int,
    booking_date: date,
    booking_time: time,
) -> None:
    """
    Повторно проверяет дату и выбранный слот перед подтверждением.

    Защищает от:
    - вручную отправленного времени;
    - устаревшей кнопки;
    - выбора даты вне календаря;
    - изменения расписания;
    - нового выходного или блокировки;
    - записи, созданной другим клиентом после показа кнопок.
    """
    today = local_today()
    last_available_date = (
        today + timedelta(
            days=BOOKING_WINDOW_DAYS - 1
        )
    )

    if booking_date < today:
        raise ValueError(
            "Выбранная дата уже прошла."
        )

    if booking_date > last_available_date:
        raise ValueError(
            "Выбранная дата находится вне доступного календаря."
        )

    available_slots = get_available_slots(
        db=db,
        master_id=master_id,
        service_id=service_id,
        booking_date=booking_date,
    )

    if booking_time not in available_slots:
        raise ValueError(
            "Выбранное время больше недоступно. "
            "Выберите другой свободный слот."
        )
