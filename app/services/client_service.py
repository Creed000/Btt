from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.client import Client


class ClientService:

    @staticmethod
    def create_if_not_exists(
        db: Session,
        user_id: int,
    ) -> Client:
        """
        Возвращает существующий профиль клиента
        или создаёт новый.
        """
        client = db.scalar(
            select(Client).where(
                Client.user_id == user_id
            )
        )

        if client is not None:
            return client

        client = Client(
            user_id=user_id,
            bonus_points=0,
            total_visits=0,
        )

        try:
            db.add(client)
            db.commit()
            db.refresh(client)

            return client

        except Exception:
            db.rollback()
            raise
