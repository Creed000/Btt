from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.bookings import create_booking
from app.models.booking import Booking
from app.models.user import User


class BookingRepository:

    @staticmethod
    def get_by_id(
        db: Session,
        booking_id: int,
    ) -> Booking | None:
        return db.scalar(
            select(Booking).where(
                Booking.id == booking_id
            )
        )

    @staticmethod
    def get_by_master(
        db: Session,
        master_id: int,
    ) -> list[Booking]:
        return list(
            db.scalars(
                select(Booking).where(
                    Booking.master_id == master_id
                )
            ).all()
        )

    @staticmethod
    def get_by_client(
        db: Session,
        client_id: int,
    ) -> list[Booking]:
        return list(
            db.scalars(
                select(Booking).where(
                    Booking.client_id == client_id
                )
            ).all()
        )

    @staticmethod
    def create(
        db: Session,
        booking: Booking,
    ) -> Booking:
        """
        Совместимый legacy API.

        Не создаёт Booking напрямую. Все новые записи
        проходят только через app.database.bookings.create_booking().
        """
        if booking.status not in (None, "new"):
            raise ValueError(
                "Новая запись может быть создана "
                "только со статусом 'new'."
            )

        telegram_id = db.scalar(
            select(User.telegram_id).where(
                User.id == booking.client_id
            )
        )

        if telegram_id is None:
            raise ValueError(
                "Клиент больше не существует."
            )

        return create_booking(
            telegram_id=telegram_id,
            master_id=booking.master_id,
            service_id=booking.service_id,
            booking_date=booking.booking_date,
            booking_time=booking.booking_time,
        )

    @staticmethod
    def update(
        db: Session,
        booking: Booking,
    ) -> Booking:
        """
        Универсальное сохранение Booking запрещено.

        Статус и другие критичные поля записи должны
        изменяться только специализированными handler/service
        с row-lock и проверкой допустимого перехода.
        """
        raise RuntimeError(
            "Прямое обновление Booking запрещено. "
            "Используйте специализированную функцию "
            "изменения записи."
        )

    @staticmethod
    def delete(
        db: Session,
        booking: Booking,
    ) -> None:
        """
        Физическое удаление Booking из рабочего кода запрещено.
        Для отмены используется status='cancelled'.
        """
        raise RuntimeError(
            "Прямое удаление Booking запрещено. "
            "Для отмены изменяйте статус через "
            "специализированный handler/service."
        )
