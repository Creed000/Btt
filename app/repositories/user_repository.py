from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:

    @staticmethod
    def get_by_telegram_id(
        db: Session,
        telegram_id: int,
    ) -> User | None:
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
        role: str = "client",
        timezone: str = "Europe/Moscow",
    ) -> User:

        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            role=role,
            timezone=timezone,
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        return user

    @staticmethod
    def update(
        db: Session,
        user: User,
    ) -> User:
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def delete(
        db: Session,
        user: User,
    ) -> None:
        db.delete(user)
        db.commit()
