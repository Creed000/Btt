from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:

    @staticmethod
    def get_by_telegram_id(db: Session, telegram_id: int):
        return db.scalar(
            select(User).where(User.telegram_id == telegram_id)
        )

    @staticmethod
    def create(
        db: Session,
        telegram_id: int,
        username: str | None,
        first_name: str,
        last_name: str | None,
    ):
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        return user
