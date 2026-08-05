import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)


def upgrade_user_notification_settings() -> None:
    """
    Добавляет users.notifications_enabled в существующую базу.

    Новые пользователи получают True из модели User.
    Для старых пользователей устанавливается True,
    чтобы текущие уведомления продолжили работать.
    """
    inspector = inspect(engine)

    if "users" not in inspector.get_table_names():
        logger.info(
            "Таблица users ещё не создана. "
            "Обновление уведомлений пропущено."
        )
        return

    column_names = {
        column["name"]
        for column in inspector.get_columns("users")
    }

    if "notifications_enabled" in column_names:
        logger.info(
            "Колонка users.notifications_enabled уже существует."
        )
        return

    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(
                text(
                    """
                    ALTER TABLE users
                    ADD COLUMN notifications_enabled BOOLEAN
                    NOT NULL DEFAULT TRUE
                    """
                )
            )

            connection.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS
                    ix_users_notifications_enabled
                    ON users (notifications_enabled)
                    """
                )
            )

        elif engine.dialect.name == "sqlite":
            connection.execute(
                text(
                    """
                    ALTER TABLE users
                    ADD COLUMN notifications_enabled BOOLEAN
                    NOT NULL DEFAULT 1
                    """
                )
            )

        else:
            raise RuntimeError(
                "Неподдерживаемая база данных: "
                f"{engine.dialect.name}"
            )

    logger.info(
        "Колонка users.notifications_enabled успешно добавлена."
    )
