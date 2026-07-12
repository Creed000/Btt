from sqlalchemy.orm import Session

from app.repositories.user_repository import UserRepository


class UserService:

    @staticmethod
    def register(db: Session, tg_user):

        user = UserRepository.get_by_telegram_id(
            db,
            tg_user.id,
        )

        if user:
            return user

        return UserRepository.create(
            db=db,
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
        )
