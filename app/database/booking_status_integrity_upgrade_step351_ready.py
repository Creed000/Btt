import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)
CONSTRAINT_NAME = "ck_bookings_status_valid"
VALID_STATUSES = (
    "new",
    "confirmed",
    "completed",
    "cancelled",
)


def upgrade_booking_status_integrity() -> None:
    """
    Защищает bookings.status на уровне БД.

    Перед добавлением constraint старые данные проверяются.
    Неизвестные/NULL статусы автоматически не исправляются.
    """
    inspector = inspect(engine)

    if "bookings" not in inspector.get_table_names():
        return

    columns = {
        column["name"]
        for column in inspector.get_columns("bookings")
    }

    if "status" not in columns:
        logger.warning(
            "Не удалось проверить bookings.status: колонка отсутствует."
        )
        return

    with engine.begin() as connection:
        invalid = connection.execute(
            text(
                """
                SELECT id, status
                FROM bookings
                WHERE status IS NULL
                   OR status NOT IN (
                       'new',
                       'confirmed',
                       'completed',
                       'cancelled'
                   )
                ORDER BY id
                LIMIT 20
                """
            )
        ).all()

        if invalid:
            details = "; ".join(
                f"id={row.id}, status={row.status!r}"
                for row in invalid
            )
            raise RuntimeError(
                "В bookings найдены недопустимые статусы. "
                "Исправьте их перед запуском DB constraint. "
                f"Найдены: {details}"
            )

        if engine.dialect.name == "postgresql":
            # DB-default защищает также INSERT вне ORM.
            connection.execute(
                text(
                    "ALTER TABLE bookings "
                    "ALTER COLUMN status SET DEFAULT 'new'"
                )
            )

            existing_constraints = {
                item["name"]
                for item in inspect(connection).get_check_constraints(
                    "bookings"
                )
                if item.get("name")
            }

            if CONSTRAINT_NAME not in existing_constraints:
                connection.execute(
                    text(
                        f"""
                        ALTER TABLE bookings
                        ADD CONSTRAINT {CONSTRAINT_NAME}
                        CHECK (
                            status IN (
                                'new',
                                'confirmed',
                                'completed',
                                'cancelled'
                            )
                        )
                        """
                    )
                )

        elif engine.dialect.name == "sqlite":
            # Для новых SQLite-баз constraint создаётся из ORM-модели.
            # ALTER TABLE SQLite не умеет безопасно добавить CHECK без
            # пересоздания таблицы, поэтому старую dev-базу лишь проверяем.
            logger.warning(
                "SQLite: существующая bookings проверена, но CHECK "
                "constraint добавляется только в новые базы."
            )
        else:
            logger.warning(
                "Диалект %s не поддержан для DB constraint bookings.status.",
                engine.dialect.name,
            )
            return

    logger.info(
        "Целостность bookings.status проверена и защищена."
    )
