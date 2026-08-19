import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)


def upgrade_booking_price_snapshot() -> None:
    """
    Добавляет bookings.price_amount для старых PostgreSQL-баз.

    Старые записи получают snapshot из текущего Service.price.
    После проверки колонка становится NOT NULL и получает CHECK >= 0.
    Повреждённые данные автоматически не исправляются.
    """
    inspector = inspect(engine)

    if "bookings" not in inspector.get_table_names():
        logger.info(
            "Таблица bookings ещё не создана. "
            "Price snapshot upgrade пропущен."
        )
        return

    if engine.dialect.name != "postgresql":
        logger.info(
            "Booking price snapshot upgrade пропущен для %s.",
            engine.dialect.name,
        )
        return

    columns = {
        column["name"]
        for column in inspector.get_columns("bookings")
    }

    with engine.begin() as connection:
        if "price_amount" not in columns:
            connection.execute(
                text(
                    """
                    ALTER TABLE bookings
                    ADD COLUMN price_amount INTEGER
                    """
                )
            )

        connection.execute(
            text(
                """
                UPDATE bookings AS b
                SET price_amount = s.price
                FROM services AS s
                WHERE b.service_id = s.id
                  AND b.price_amount IS NULL
                """
            )
        )

        broken_ids = list(
            connection.execute(
                text(
                    """
                    SELECT id
                    FROM bookings
                    WHERE price_amount IS NULL
                       OR price_amount < 0
                    ORDER BY id
                    LIMIT 50
                    """
                )
            ).scalars()
        )

        if broken_ids:
            raise RuntimeError(
                "Нельзя включить price snapshot Booking: "
                "найдены записи без корректной цены. "
                "Первые Booking.id: "
                + ", ".join(str(item) for item in broken_ids)
                + ". Исправьте Service.price/данные вручную "
                "и повторите запуск."
            )

        connection.execute(
            text(
                """
                ALTER TABLE bookings
                ALTER COLUMN price_amount SET NOT NULL
                """
            )
        )

        connection.execute(
            text(
                """
                ALTER TABLE bookings
                DROP CONSTRAINT IF EXISTS
                    ck_bookings_price_amount_nonnegative
                """
            )
        )

        connection.execute(
            text(
                """
                ALTER TABLE bookings
                ADD CONSTRAINT
                    ck_bookings_price_amount_nonnegative
                CHECK (price_amount >= 0)
                """
            )
        )

    logger.info("Booking price snapshot включён.")
