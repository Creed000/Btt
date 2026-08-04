import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)


def upgrade_booking_service_foreign_key() -> None:
    """
    Меняет внешний ключ bookings.service_id на ON DELETE RESTRICT.

    PostgreSQL:
    - находит только FOREIGN KEY для bookings.service_id;
    - удаляет старое ограничение;
    - создаёт безопасное ON DELETE RESTRICT.

    SQLite:
    - обновление пропускается;
    - новые базы получают RESTRICT из модели Booking.
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
                    SELECT DISTINCT tc.constraint_name
                    FROM information_schema.table_constraints AS tc
                    JOIN information_schema.key_column_usage AS kcu
                      ON tc.constraint_name = kcu.constraint_name
                     AND tc.constraint_schema = kcu.constraint_schema
                    WHERE tc.table_schema = current_schema()
                      AND tc.table_name = 'bookings'
                      AND tc.constraint_type = 'FOREIGN KEY'
                      AND kcu.column_name = 'service_id'
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
