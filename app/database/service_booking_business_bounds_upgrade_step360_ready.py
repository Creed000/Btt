import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)


SERVICE_MIN_DURATION = 15
SERVICE_MAX_DURATION = 720
SERVICE_MIN_PRICE = 0
SERVICE_MAX_PRICE = 10_000_000


def upgrade_service_booking_business_bounds() -> None:
    """
    Закрепляет бизнес-границы услуги и Booking snapshot в PostgreSQL.

    Service:
      duration 15..720 минут
      price 0..10_000_000

    Booking snapshot:
      duration_minutes 15..720
      price_amount 0..10_000_000

    Сначала проверяет старые данные. Ничего автоматически
    не исправляет и не удаляет.
    """
    inspector = inspect(engine)

    if engine.dialect.name != "postgresql":
        logger.info(
            "Business bounds upgrade пропущен для %s.",
            engine.dialect.name,
        )
        return

    tables = set(inspector.get_table_names())

    with engine.begin() as connection:
        if "services" in tables:
            bad_services = list(
                connection.execute(
                    text(
                        """
                        SELECT id, duration, price
                        FROM services
                        WHERE duration < 15
                           OR duration > 720
                           OR price < 0
                           OR price > 10000000
                        ORDER BY id
                        LIMIT 50
                        """
                    )
                ).mappings()
            )

            if bad_services:
                details = "; ".join(
                    f"id={row['id']} duration={row['duration']} price={row['price']}"
                    for row in bad_services
                )
                raise RuntimeError(
                    "Нельзя включить ограничения Service: "
                    "найдены значения вне допустимых границ. "
                    + details
                )

            connection.execute(
                text(
                    "ALTER TABLE services "
                    "DROP CONSTRAINT IF EXISTS ck_services_duration_range"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE services "
                    "DROP CONSTRAINT IF EXISTS ck_services_price_range"
                )
            )
            connection.execute(
                text(
                    """
                    ALTER TABLE services
                    ADD CONSTRAINT ck_services_duration_range
                    CHECK (duration BETWEEN 15 AND 720)
                    """
                )
            )
            connection.execute(
                text(
                    """
                    ALTER TABLE services
                    ADD CONSTRAINT ck_services_price_range
                    CHECK (price BETWEEN 0 AND 10000000)
                    """
                )
            )

        if "bookings" in tables:
            columns = {
                column["name"]
                for column in inspect(connection).get_columns("bookings")
            }

            needed = {"duration_minutes", "price_amount"}
            if not needed.issubset(columns):
                logger.info(
                    "Booking business bounds отложены: "
                    "snapshot-поля ещё не созданы."
                )
                return

            bad_bookings = list(
                connection.execute(
                    text(
                        """
                        SELECT id, duration_minutes, price_amount
                        FROM bookings
                        WHERE duration_minutes < 15
                           OR duration_minutes > 720
                           OR price_amount < 0
                           OR price_amount > 10000000
                        ORDER BY id
                        LIMIT 50
                        """
                    )
                ).mappings()
            )

            if bad_bookings:
                details = "; ".join(
                    f"id={row['id']} duration={row['duration_minutes']} price={row['price_amount']}"
                    for row in bad_bookings
                )
                raise RuntimeError(
                    "Нельзя включить ограничения Booking snapshot: "
                    "найдены значения вне допустимых границ. "
                    + details
                )

            for name in (
                "ck_bookings_duration_minutes_positive",
                "ck_bookings_duration_minutes_range",
                "ck_bookings_price_amount_nonnegative",
                "ck_bookings_price_amount_range",
            ):
                safe = name.replace('\"', '\\"')
                connection.execute(
                    text(
                        f"ALTER TABLE bookings DROP CONSTRAINT IF EXISTS {safe}"
                    )
                )

            connection.execute(
                text(
                    """
                    ALTER TABLE bookings
                    ADD CONSTRAINT ck_bookings_duration_minutes_range
                    CHECK (duration_minutes BETWEEN 15 AND 720)
                    """
                )
            )
            connection.execute(
                text(
                    """
                    ALTER TABLE bookings
                    ADD CONSTRAINT ck_bookings_price_amount_range
                    CHECK (price_amount BETWEEN 0 AND 10000000)
                    """
                )
            )

    logger.info(
        "Service/Booking business bounds включены."
    )
