from sqlalchemy.orm import Session

from app.repositories.client_repository import ClientRepository


class ClientService:

    @staticmethod
    def create_if_not_exists(db: Session, user_id: int):

        client = ClientRepository.get_by_user_id(
            db,
            user_id,
        )

        if client:
            return client

        return ClientRepository.create(
            db,
            user_id,
        )
