import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)


REMINDER_FLAGS = (
    "reminder_24h_sent",
    "reminder_2h_sent",
    "reminder_24h_client_sent",
    "reminder_24h_master_sent",
    "reminder_2h_client_sent",
    "reminder_2h_master_sent",
)

RECIPIENT_PAIRS = (
    (
        "reminder_24h_client_sent",
        "reminder_24h_client_claimed_at",
        "ck_bookings_24h_client_sent_claim_clear",
    ),
    (
        "reminder_24h_master_sent",
        "reminder_24h_master_claimed_at",
        "ck_bookings_24h_master_sent_claim_clear",
    ),
    (
        "reminder_2h_client_sent",
        "reminder_2h_client_claimed_at",
        "ck_bookings_2h_client_sent_claim_clear",
    ),
    (
        "reminder_2h_master_sent",
        "reminder_2h_master_claimed_at",
        "ck_bookings_2h_master_sent_claim_clear",
    ),
)


def upgrade_booking_reminder_integrity() -> None:
    """
    Укрепляет reminder-state таблицы bookings.

    Гарантирует:
    - все reminder *_sent флаги NOT NULL DEFAULT false;
    - sent=true не может сосуществовать с активным claimed_at;
    - claim timestamps остаются nullable намеренно.

    Старые некорректные данные автоматически не исправляются.
    """
    inspector = inspect(engine)

    if "bookings" not in inspector.get_table_names():
        logger.info(
            "Таблица bookings ещё не создана. "
            "Reminder integrity upgrade пропущен."
        )
        return

    if engine.dialect.name != "postgresql":
        logger.info(
            "Booking reminder integrity upgrade пропущен для %s.",
            engine.dialect.name,
        )
        return

    columns = {
        column["name"]
        for column in inspector.get_columns("bookings")
    }

    required = set(REMINDER_FLAGS)

    for sent_name, claim_name, _ in RECIPIENT_PAIRS:
        required.add(sent_name)
        required.add(claim_name)

    missing = sorted(required - columns)

    if missing:
        raise RuntimeError(
            "В bookings отсутствуют reminder-поля: "
            + ", ".join(missing)
        )

    with engine.begin() as connection:
        null_flag_rows = list(
            connection.execute(
                text(
                    """
                    SELECT id
                    FROM bookings
                    WHERE reminder_24h_sent IS NULL
                       OR reminder_2h_sent IS NULL
                       OR reminder_24h_client_sent IS NULL
                       OR reminder_24h_master_sent IS NULL
                       OR reminder_2h_client_sent IS NULL
                       OR reminder_2h_master_sent IS NULL
                    ORDER BY id
                    LIMIT 50
                    """
                )
            ).scalars()
        )

        if null_flag_rows:
            raise RuntimeError(
                "Нельзя включить reminder integrity: "
                "найдены NULL reminder-флаги. "
                "Первые Booking.id: "
                + ", ".join(
                    str(item)
                    for item in null_flag_rows
                )
            )

        bad_claim_rows = list(
            connection.execute(
                text(
                    """
                    SELECT id
                    FROM bookings
                    WHERE (
                        reminder_24h_client_sent = true
                        AND reminder_24h_client_claimed_at IS NOT NULL
                    )
                    OR (
                        reminder_24h_master_sent = true
                        AND reminder_24h_master_claimed_at IS NOT NULL
                    )
                    OR (
                        reminder_2h_client_sent = true
                        AND reminder_2h_client_claimed_at IS NOT NULL
                    )
                    OR (
                        reminder_2h_master_sent = true
                        AND reminder_2h_master_claimed_at IS NOT NULL
                    )
                    ORDER BY id
                    LIMIT 50
                    """
                )
            ).scalars()
        )

        if bad_claim_rows:
            raise RuntimeError(
                "Нельзя включить reminder integrity: "
                "есть отправленные reminders с незакрытым claim. "
                "Первые Booking.id: "
                + ", ".join(
                    str(item)
                    for item in bad_claim_rows
                )
            )

        for flag_name in REMINDER_FLAGS:
            connection.execute(
                text(
                    f"""
                    ALTER TABLE bookings
                    ALTER COLUMN {flag_name}
                    SET DEFAULT false
                    """
                )
            )
            connection.execute(
                text(
                    f"""
                    ALTER TABLE bookings
                    ALTER COLUMN {flag_name}
                    SET NOT NULL
                    """
                )
            )

        for sent_name, claim_name, constraint_name in RECIPIENT_PAIRS:
            connection.execute(
                text(
                    f"""
                    ALTER TABLE bookings
                    DROP CONSTRAINT IF EXISTS {constraint_name}
                    """
                )
            )

            connection.execute(
                text(
                    f"""
                    ALTER TABLE bookings
                    ADD CONSTRAINT {constraint_name}
                    CHECK (
                        NOT {sent_name}
                        OR {claim_name} IS NULL
                    )
                    """
                )
            )

    logger.info(
        "Booking reminder integrity включена."
    )
