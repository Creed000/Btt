from datetime import date, time

from app.database.session import SessionLocal
from app.models.booking import Booking
from app.repositories.booking_repository import BookingRepository


def save_booking(
    client_id: int,
    master_id: int,
    service_id: int,
    booking_date: date,
    booking_time: time,
    status: str = "new",
) -> Booking:
    """
    Сохраняет запись через BookingRepository.

    Основной клиентский процесс записи использует
    app.database.bookings.create_booking(), где выполняются все проверки
    расписания, подписки и пересечений. Эта функция оставлена для
    совместимости со старым сервисным слоем.
    """
    db = SessionLocal()

    try:
        booking = Booking(
            client_id=client_id,
            master_id=master_id,
            service_id=service_id,
            booking_date=booking_date,
            booking_time=booking_time,
            status=status,
        )

        return BookingRepository.create(
            db,
            booking,
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()
