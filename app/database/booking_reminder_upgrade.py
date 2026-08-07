import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)


def upgrade_booking_reminder_delivery_flags() -> None:
    """
    Идемпотентно добавляет раздельные флаги доставки
    напоминаний клиенту и мастеру.

    Старые reminder_24h_sent/reminder_2h_sent используются
    для backfill, чтобы после обновления не отправить
    уже доставленные старые напоминания повторно.
    """
    inspector = inspect(engine)

    if "bookings" not in inspector.get_table_names():
        return

    columns = {
        column["name"]
        for column in inspector.get_columns("bookings")
    }

    dialect = engine.dialect.name

    definitions = {
        "reminder_24h_client_sent": (
            "BOOLEAN NOT NULL DEFAULT FALSE",
            "BOOLEAN NOT NULL DEFAULT 0",
        ),
        "reminder_24h_master_sent": (
            "BOOLEAN NOT NULL DEFAULT FALSE",
            "BOOLEAN NOT NULL DEFAULT 0",
        ),
        "reminder_2h_client_sent": (
            "BOOLEAN NOT NULL DEFAULT FALSE",
            "BOOLEAN NOT NULL DEFAULT 0",
        ),
        "reminder_2h_master_sent": (
            "BOOLEAN NOT NULL DEFAULT FALSE",
            "BOOLEAN NOT NULL DEFAULT 0",
        ),
    }

    with engine.begin() as connection:
        for column_name, definitions_by_dialect in definitions.items():
            if column_name in columns:
                continue

            postgres_definition, sqlite_definition = definitions_by_dialect
            definition = (
                sqlite_definition
                if dialect == "sqlite"
                else postgres_definition
            )

            connection.execute(
                text(
                    f"ALTER TABLE bookings "
                    f"ADD COLUMN {column_name} {definition}"
                )
            )

            columns.add(column_name)

            logger.info(
                "Добавлена колонка bookings.%s",
                column_name,
            )

        # Если старый общий флаг уже был true,
        # считаем напоминание доставленным обоим,
        # чтобы не создавать дублей после миграции.
        if "reminder_24h_sent" in columns:
            connection.execute(
                text(
                    """
                    UPDATE bookings
                    SET reminder_24h_client_sent = TRUE,
                        reminder_24h_master_sent = TRUE
                    WHERE reminder_24h_sent = TRUE
                    """
                )
            )

        if "reminder_2h_sent" in columns:
            connection.execute(
                text(
                    """
                    UPDATE bookings
                    SET reminder_2h_client_sent = TRUE,
                        reminder_2h_master_sent = TRUE
                    WHERE reminder_2h_sent = TRUE
                    """
                )
            )

        # Полезный индекс для фонового job.
        if dialect == "postgresql":
            connection.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS
                    ix_bookings_status_booking_date
                    ON bookings (status, booking_date)
                    """
                )
            )

    logger.info(
        "Раздельные флаги напоминаний проверены."
    )
