import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)


def upgrade_booking_duration_snapshot() -> None:
    """
    Добавляет bookings.duration_minutes для старых PostgreSQL-баз.

    Старые записи получают snapshot из текущего Service.duration.
    После проверки колонка становится NOT NULL и получает CHECK > 0.
    """
    inspector = inspect(engine)

    if "bookings" not in inspector.get_table_names():
        logger.info(
            "Таблица bookings ещё не создана. "
            "Duration snapshot upgrade пропущен."
        )
        return

    if engine.dialect.name != "postgresql":
        logger.info(
            "Booking duration snapshot upgrade пропущен для %s.",
            engine.dialect.name,
        )
        return

    columns = {
        column["name"]
        for column in inspector.get_columns("bookings")
    }

    with engine.begin() as connection:
        if "duration_minutes" not in columns:
            connection.execute(
                text(
                    """
                    ALTER TABLE bookings
                    ADD COLUMN duration_minutes INTEGER
                    """
                )
            )

        connection.execute(
            text(
                """
                UPDATE bookings AS b
                SET duration_minutes = s.duration
                FROM services AS s
                WHERE b.service_id = s.id
                  AND b.duration_minutes IS NULL
                """
            )
        )

        broken_ids = list(
            connection.execute(
                text(
                    """
                    SELECT id
                    FROM bookings
                    WHERE duration_minutes IS NULL
                       OR duration_minutes <= 0
                    ORDER BY id
                    LIMIT 50
                    """
                )
            ).scalars()
        )

        if broken_ids:
            raise RuntimeError(
                "Нельзя включить duration snapshot Booking: "
                "найдены записи без корректной длительности. "
                "Первые Booking.id: "
                + ", ".join(str(item) for item in broken_ids)
                + ". Исправьте данные вручную и повторите запуск."
            )

        connection.execute(
            text(
                """
                ALTER TABLE bookings
                ALTER COLUMN duration_minutes SET NOT NULL
                """
            )
        )

        connection.execute(
            text(
                """
                ALTER TABLE bookings
                DROP CONSTRAINT IF EXISTS
                    ck_bookings_duration_minutes_positive
                """
            )
        )

        connection.execute(
            text(
                """
                ALTER TABLE bookings
                ADD CONSTRAINT
                    ck_bookings_duration_minutes_positive
                CHECK (duration_minutes > 0)
                """
            )
        )

    logger.info("Booking duration snapshot включён.")
