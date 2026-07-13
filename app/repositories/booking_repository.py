from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.booking import Booking


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
        db.add(booking)
        db.commit()
        db.refresh(booking)
        return booking

    @staticmethod
    def update(
        db: Session,
        booking: Booking,
    ) -> Booking:
        db.add(booking)
        db.commit()
        db.refresh(booking)
        return booking

    @staticmethod
    def delete(
        db: Session,
        booking: Booking,
    ) -> None:
        db.delete(booking)
        db.commit()
