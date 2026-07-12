from app.repositories.booking_repository import create_booking


def save_booking(
    client_id,
    master_id,
    service_id,
    booking_date,
    booking_time,
):
    return create_booking(
        client_id,
        master_id,
        service_id,
        booking_date,
        booking_time,
    )
