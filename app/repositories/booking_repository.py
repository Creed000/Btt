from app.database.session import SessionLocal
from app.models.booking import Booking


def create_booking(
    client_id,
    master_id,
    service_id,
    booking_date,
    booking_time,
):

    db = SessionLocal()

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
    db.close()

    return booking
