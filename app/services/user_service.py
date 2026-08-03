from sqlalchemy.orm import Session

from app.config.settings import settings
from app.models.user import User
from app.repositories.user_repository import UserRepository


class UserService:

    @staticmethod
    def register(db: Session, tg_user) -> User:
        user = UserRepository.get_by_telegram_id(
            db,
            tg_user.id,
        )

        owner_role = (
            settings.ADMIN_TELEGRAM_ID is not None
            and tg_user.id == settings.ADMIN_TELEGRAM_ID
        )

        if user:
            user.username = tg_user.username
            user.first_name = tg_user.first_name
            user.last_name = tg_user.last_name

            if owner_role:
                user.role = "owner"

            db.commit()
            db.refresh(user)
            return user

        role = "owner" if owner_role else "client"

        return UserRepository.create(
            db=db,
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
            role=role,
        )
