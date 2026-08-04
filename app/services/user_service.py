from sqlalchemy.orm import Session

from app.config.settings import settings
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.timezone import local_naive_now


class UserService:

    @staticmethod
    def register(
        db: Session,
        tg_user,
    ) -> User:
        telegram_id = int(tg_user.id)

        configured_role = settings.role_for_telegram_id(
            telegram_id
        )

        first_name = (
            tg_user.first_name
            or "Пользователь"
        )

        user = UserRepository.get_by_telegram_id(
            db,
            telegram_id,
        )

        try:
            if user is not None:
                user.username = tg_user.username
                user.first_name = first_name
                user.last_name = tg_user.last_name
                user.last_seen = local_naive_now()

                # OWNER_TELEGRAM_ID и ADMIN_TELEGRAM_IDS
                # имеют приоритет над текущей ролью.
                if configured_role is not None:
                    user.role = configured_role

                db.add(user)
                db.commit()
                db.refresh(user)

                return user

            role = configured_role or "client"

            user = UserRepository.create(
                db=db,
                telegram_id=telegram_id,
                username=tg_user.username,
                first_name=first_name,
                last_name=tg_user.last_name,
                role=role,
                timezone=settings.APP_TIMEZONE,
            )

            user.last_seen = local_naive_now()
            db.add(user)
            db.commit()
            db.refresh(user)

            return user

        except Exception:
            db.rollback()
            raise
