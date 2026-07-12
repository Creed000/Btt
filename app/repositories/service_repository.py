from app.database.session import SessionLocal
from app.models.service import Service


def get_service(service_id: int):

    db = SessionLocal()

    service = (
        db.query(Service)
        .filter(Service.id == service_id)
        .first()
    )

    db.close()

    return service


def get_services_by_master(master_id: int):

    db = SessionLocal()

    services = (
        db.query(Service)
        .filter(Service.master_id == master_id)
        .all()
    )

    db.close()

    return services
