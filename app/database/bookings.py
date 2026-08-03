from datetime import date, time

from sqlalchemy import select

from app.database.session import SessionLocal
from app.models.booking import Booking
from app.models.user import User


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
            select(User).where(User.telegram_id == telegram_id)
        )
        if user is None:
            raise ValueError("Пользователь не зарегистрирован. Отправьте /start.")

        busy_booking = db.scalar(
            select(Booking).where(
                Booking.master_id == master_id,
                Booking.booking_date == booking_date,
                Booking.booking_time == booking_time,
                Booking.status.in_(["new", "confirmed"]),
            )
        )
        if busy_booking is not None:
            raise ValueError("Это время уже занято. Выберите другой слот.")

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
        db.refresh(booking)
        return booking

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
