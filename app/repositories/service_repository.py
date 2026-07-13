from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.service import Service


class ServiceRepository:

    @staticmethod
    def get_by_id(
        db: Session,
        service_id: int,
    ) -> Service | None:
        return db.scalar(
            select(Service).where(Service.id == service_id)
        )

    @staticmethod
    def get_by_master(
        db: Session,
        master_id: int,
    ) -> list[Service]:
        return list(
            db.scalars(
                select(Service).where(
                    Service.master_id == master_id
                )
            ).all()
        )

    @staticmethod
    def create(
        db: Session,
        service: Service,
    ) -> Service:
        db.add(service)
        db.commit()
        db.refresh(service)
        return service

    @staticmethod
    def update(
        db: Session,
        service: Service,
    ) -> Service:
        db.add(service)
        db.commit()
        db.refresh(service)
        return service

    @staticmethod
    def delete(
        db: Session,
        service: Service,
    ) -> None:
        db.delete(service)
        db.commit()
