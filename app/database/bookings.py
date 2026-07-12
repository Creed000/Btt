from app.database.session import SessionLocal
from app.models.booking import Booking
from datetime import datetime


def create_booking(client_id, service_id, booking_time):
    db = SessionLocal()

    booking = Booking(
        client_id=client_id,
        service_id=service_id,
        booking_time=booking_time,
        status="new"
    )

    db.add(booking)
    db.commit()
    db.refresh(booking)
    db.close()

    return booking
