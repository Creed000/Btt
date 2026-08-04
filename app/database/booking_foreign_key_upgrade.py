import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)


def upgrade_booking_service_foreign_key() -> None:
    """
    Меняет внешний ключ bookings.service_id на ON DELETE RESTRICT.

    PostgreSQL:
    - находит все внешние ключи таблицы bookings для service_id;
    - удаляет старое ограничение, включая ON DELETE CASCADE;
    - создаёт новое ограничение ON DELETE RESTRICT.

    SQLite:
    - ничего не меняет, потому что ALTER CONSTRAINT там не поддерживается;
    - новые SQLite-базы получат RESTRICT из модели Booking.
    """
    if engine.dialect.name != "postgresql":
        logger.info(
            "Обновление FK bookings.service_id пропущено: "
            "используется не PostgreSQL."
        )
        return

    inspector = inspect(engine)

    if "bookings" not in inspector.get_table_names():
        logger.info(
            "Таблица bookings ещё не создана. "
            "Обновление внешнего ключа пропущено."
        )
        return

    with engine.begin() as connection:
        constraint_names = list(
            connection.execute(
                text(
                    """
                    SELECT DISTINCT constraint_name
                    FROM information_schema.key_column_usage
                    WHERE table_schema = current_schema()
                      AND table_name = 'bookings'
                      AND column_name = 'service_id'
                      AND constraint_name IS NOT NULL
                    """
                )
            ).scalars()
        )

        for constraint_name in constraint_names:
            safe_name = constraint_name.replace(
                '"',
                '""',
            )

            connection.execute(
                text(
                    f'ALTER TABLE bookings '
                    f'DROP CONSTRAINT IF EXISTS "{safe_name}"'
                )
            )

        connection.execute(
            text(
                """
                ALTER TABLE bookings
                ADD CONSTRAINT fk_bookings_service_id
                FOREIGN KEY (service_id)
                REFERENCES services (id)
                ON DELETE RESTRICT
                """
            )
        )

    logger.info(
        "Внешний ключ bookings.service_id обновлён: "
        "ON DELETE RESTRICT."
    )
