import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)


def upgrade_master_booking_default() -> None:
    """
    Ставит безопасный server default FALSE для masters.booking_enabled.

    Существующие значения не изменяются. На PostgreSQL меняется только
    DEFAULT для будущих INSERT, где поле не указано явно.
    """
    inspector = inspect(engine)

    if "masters" not in inspector.get_table_names():
        return

    columns = {
        column["name"]
        for column in inspector.get_columns("masters")
    }

    if "booking_enabled" not in columns:
        logger.warning(
            "Не удалось выставить DEFAULT FALSE: "
            "masters.booking_enabled отсутствует."
        )
        return

    dialect = engine.dialect.name

    if dialect == "postgresql":
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    ALTER TABLE masters
                    ALTER COLUMN booking_enabled
                    SET DEFAULT FALSE
                    """
                )
            )

        logger.info(
            "PostgreSQL default masters.booking_enabled = FALSE установлен."
        )
        return

    if dialect == "sqlite":
        # SQLite не умеет безопасно ALTER COLUMN SET DEFAULT без
        # пересоздания таблицы. Новые SQLite-базы получат server_default
        # из ORM-модели через create_all(). Старые значения не трогаем.
        logger.info(
            "SQLite: существующая таблица не перестраивается; "
            "server_default FALSE применяется для новых схем."
        )
        return

    logger.warning(
        "Диалект %s не поддержан для изменения server default.",
        dialect,
    )
