import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)


ACTIVE_STATUSES_SQL = "'new', 'confirmed'"


def _duplicate_groups(
    connection,
    owner_column: str,
) -> list[dict]:
    return list(
        connection.execute(
            text(
                f"""
                SELECT
                    {owner_column} AS owner_id,
                    booking_date,
                    booking_time,
                    array_agg(id ORDER BY id) AS booking_ids,
                    COUNT(*) AS duplicate_count
                FROM bookings
                WHERE status IN ({ACTIVE_STATUSES_SQL})
                GROUP BY
                    {owner_column},
                    booking_date,
                    booking_time
                HAVING COUNT(*) > 1
                ORDER BY booking_date, booking_time
                LIMIT 50
                """
            )
        ).mappings()
    )


def _format_duplicates(
    groups: list[dict],
    label: str,
) -> str:
    parts = []

    for group in groups:
        ids = ",".join(
            str(item)
            for item in group["booking_ids"]
        )
        parts.append(
            f"{label}={group['owner_id']} "
            f"{group['booking_date']} "
            f"{group['booking_time']} "
            f"Booking.id=[{ids}]"
        )

    return "; ".join(parts)


def upgrade_booking_active_slot_uniqueness() -> None:
    """
    Гарантирует на уровне PostgreSQL, что две активные записи
    не могут иметь одинаковые дату/время:

    - для одного мастера;
    - для одного клиента.

    Ограничение действует только для status IN ('new', 'confirmed').
    completed/cancelled историю не блокируют.

    Перед созданием индексов существующие данные проверяются.
    Дубли автоматически не удаляются.
    """
    inspector = inspect(engine)

    if "bookings" not in inspector.get_table_names():
        logger.info(
            "Таблица bookings ещё не создана. "
            "Active slot uniqueness upgrade пропущен."
        )
        return

    if engine.dialect.name != "postgresql":
        logger.info(
            "Booking active slot uniqueness upgrade "
            "пропущен для %s.",
            engine.dialect.name,
        )
        return

    required_columns = {
        "id",
        "client_id",
        "master_id",
        "booking_date",
        "booking_time",
        "status",
    }

    current_columns = {
        column["name"]
        for column in inspector.get_columns("bookings")
    }

    missing_columns = sorted(
        required_columns - current_columns
    )

    if missing_columns:
        raise RuntimeError(
            "В bookings отсутствуют обязательные поля: "
            + ", ".join(missing_columns)
        )

    with engine.begin() as connection:
        master_duplicates = _duplicate_groups(
            connection,
            "master_id",
        )
        client_duplicates = _duplicate_groups(
            connection,
            "client_id",
        )

        problems = []

        if master_duplicates:
            problems.append(
                "дубли мастера: "
                + _format_duplicates(
                    master_duplicates,
                    "master_id",
                )
            )

        if client_duplicates:
            problems.append(
                "дубли клиента: "
                + _format_duplicates(
                    client_duplicates,
                    "client_id",
                )
            )

        if problems:
            raise RuntimeError(
                "Нельзя включить уникальность активных слотов "
                "Booking: найдены существующие дубли. "
                + " | ".join(problems)
                + ". Исправьте их вручную и повторите запуск."
            )

        connection.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                    uq_bookings_active_master_slot
                ON bookings (
                    master_id,
                    booking_date,
                    booking_time
                )
                WHERE status IN ('new', 'confirmed')
                """
            )
        )

        connection.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                    uq_bookings_active_client_slot
                ON bookings (
                    client_id,
                    booking_date,
                    booking_time
                )
                WHERE status IN ('new', 'confirmed')
                """
            )
        )

    logger.info(
        "Booking active slot uniqueness включена "
        "для мастера и клиента."
    )
