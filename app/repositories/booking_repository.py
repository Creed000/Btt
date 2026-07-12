from sqlalchemy.orm import Session

from app.models.booking import Booking


def create_booking(
    db: Session,
    client_id: int,
    master_id: int,
    service_id: int,
    booking_date,
    booking_time,
):
    booking = Booking(
        client_id=client_id,
        master_id=master_id,
        service_id=service_id,
        booking_date=booking_date,
        booking_time=booking_time,
    )

    db.add(booking)
    db.commit()
    db.refresh(booking)

    return booking
