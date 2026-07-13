from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.master import Master


class MasterRepository:

    @staticmethod
    def get_by_id(
        db: Session,
        master_id: int,
    ) -> Master | None:
        return db.scalar(
            select(Master).where(Master.id == master_id)
        )

    @staticmethod
    def get_all(
        db: Session,
    ) -> list[Master]:
        return list(
            db.scalars(
                select(Master)
            ).all()
        )

    @staticmethod
    def get_by_user_id(
        db: Session,
        user_id: int,
    ) -> Master | None:
        return db.scalar(
            select(Master).where(Master.user_id == user_id)
        )

    @staticmethod
    def get_by_slug(
        db: Session,
        slug: str,
    ) -> Master | None:
        return db.scalar(
            select(Master).where(Master.slug == slug)
        )

    @staticmethod
    def update(
        db: Session,
        master: Master,
    ) -> Master:
        db.add(master)
        db.commit()
        db.refresh(master)
        return master

    @staticmethod
    def delete(
        db: Session,
        master: Master,
    ) -> None:
        db.delete(master)
        db.commit()
