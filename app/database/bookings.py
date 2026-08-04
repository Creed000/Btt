from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.database.session import SessionLocal
from app.models.booking import Booking
from app.models.master import Master
from app.models.service import Service
from app.models.user import User


ACTIVE_BOOKING_STATUSES = {
    "new",
    "confirmed",
}


def _intervals_overlap(
    first_start: datetime,
    first_end: datetime,
    second_start: datetime,
    second_end: datetime,
) -> bool:
    return first_start < second_end and second_start < first_end


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
            select(Master).where(
                Master.id == master_id,
                Master.booking_enabled.is_(True),
            )
        )

        if master is None:
            raise ValueError(
                "Мастер не найден или временно не принимает записи."
            )

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
