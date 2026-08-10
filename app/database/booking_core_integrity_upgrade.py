import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)


CORE_BOOKING_COLUMNS = (
    "client_id",
    "master_id",
    "service_id",
    "booking_date",
    "booking_time",
)


def upgrade_booking_core_integrity() -> None:
    """
    Защищает обязательные поля Booking в старой PostgreSQL-базе.

    Перед SET NOT NULL сначала проверяет существующие строки.
    Если найдены повреждённые записи, миграция останавливается
    и показывает их id — данные автоматически не изменяются.
    """
    inspector = inspect(engine)

    if "bookings" not in inspector.get_table_names():
        logger.info(
            "Таблица bookings ещё не создана. "
            "Core integrity upgrade пропущен."
        )
        return

    columns = {
        column["name"]: column
        for column in inspector.get_columns("bookings")
    }

    missing_columns = [
        name
        for name in CORE_BOOKING_COLUMNS
        if name not in columns
    ]

    if missing_columns:
        raise RuntimeError(
            "В таблице bookings отсутствуют обязательные "
            "колонки: "
            + ", ".join(missing_columns)
        )

    if engine.dialect.name != "postgresql":
        logger.info(
            "Booking core NOT NULL upgrade пропущен для %s: "
            "новые таблицы получают ограничения из ORM.",
            engine.dialect.name,
        )
        return

    null_predicate = " OR ".join(
        f"{name} IS NULL"
        for name in CORE_BOOKING_COLUMNS
    )

    with engine.begin() as connection:
        broken_rows = connection.execute(
            text(
                f"""
                SELECT
                    id,
                    client_id,
                    master_id,
                    service_id,
                    booking_date,
                    booking_time
                FROM bookings
                WHERE {null_predicate}
                ORDER BY id
                LIMIT 50
                """
            )
        ).mappings().all()

        if broken_rows:
            broken_ids = ", ".join(
                str(row["id"])
                for row in broken_rows
            )

            raise RuntimeError(
                "Нельзя включить NOT NULL для bookings: "
                "найдены повреждённые записи с пустыми "
                "обязательными полями. "
                f"Первые id: {broken_ids}. "
                "Исправьте эти записи вручную и повторите запуск."
            )

        for column_name in CORE_BOOKING_COLUMNS:
            connection.execute(
                text(
                    f"""
                    ALTER TABLE bookings
                    ALTER COLUMN {column_name} SET NOT NULL
                    """
                )
            )

    logger.info(
        "Booking core integrity обновлена: "
        "client_id/master_id/service_id/booking_date/"
        "booking_time теперь NOT NULL."
    )
