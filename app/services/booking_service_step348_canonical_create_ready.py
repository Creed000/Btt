from datetime import date, time

from sqlalchemy import select

from app.database.bookings import create_booking
from app.database.session import SessionLocal
from app.models.booking import Booking
from app.models.user import User


def save_booking(
    client_id: int,
    master_id: int,
    service_id: int,
    booking_date: date,
    booking_time: time,
    status: str = "new",
) -> Booking:
    """
    Совместимый legacy API.

    Реальное создание записи выполняется только через
    app.database.bookings.create_booking(), чтобы нельзя
    было обойти проверки расписания, подписки, пересечений
    и конкурентные блокировки.

    Legacy-параметр client_id преобразуется в telegram_id.
    Создание сразу с произвольным статусом запрещено:
    новая запись всегда начинается со статуса "new".
    """
    if status != "new":
        raise ValueError(
            "Новая запись может быть создана "
            "только со статусом 'new'."
        )

    db = SessionLocal()

    try:
        telegram_id = db.scalar(
            select(User.telegram_id).where(
                User.id == client_id
            )
        )

        if telegram_id is None:
            raise ValueError(
                "Клиент больше не существует."
            )

    finally:
        db.close()

    return create_booking(
        telegram_id=telegram_id,
        master_id=master_id,
        service_id=service_id,
        booking_date=booking_date,
        booking_time=booking_time,
    )
