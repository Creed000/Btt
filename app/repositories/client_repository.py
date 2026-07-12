from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.client import Client


class ClientRepository:

    @staticmethod
    def get_by_user_id(db: Session, user_id: int):
        return db.scalar(
            select(Client).where(Client.user_id == user_id)
        )

    @staticmethod
    def create(db: Session, user_id: int):
        client = Client(
            user_id=user_id
        )

        db.add(client)
        db.commit()
        db.refresh(client)

        return client
