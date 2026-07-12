from app.repositories.booking_repository import create_booking


def save_booking(
    db,
    client_id,
    master_id,
    service_id,
    booking_date,
    booking_time,
):
    return create_booking(
        db=db,
        client_id=client_id,
        master_id=master_id,
        service_id=service_id,
        booking_date=booking_date,
        booking_time=booking_time,
    )
