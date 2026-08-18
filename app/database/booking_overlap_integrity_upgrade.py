import logging

from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError

from app.database.session import engine


logger = logging.getLogger(__name__)


ACTIVE_STATUS_SQL = "'new', 'confirmed'"


def _overlap_pairs(
    connection,
    owner_column: str,
) -> list[dict]:
    """
    Ищет пересекающиеся активные записи одного владельца слота.

    Интервалы считаются полуоткрытыми [start, end), поэтому запись,
    начинающаяся ровно в момент окончания предыдущей, допустима.
    """
    return list(
        connection.execute(
            text(
                f"""
                SELECT
                    a.id AS booking_a_id,
                    b.id AS booking_b_id,
                    a.{owner_column} AS owner_id
                FROM bookings AS a
                JOIN bookings AS b
                  ON a.id < b.id
                 AND a.{owner_column} = b.{owner_column}
                 AND a.status IN ({ACTIVE_STATUS_SQL})
                 AND b.status IN ({ACTIVE_STATUS_SQL})
                 AND tsrange(
                        a.booking_date + a.booking_time,
                        (a.booking_date + a.booking_time)
                            + make_interval(
                                mins => a.duration_minutes
                              ),
                        '[)'
                     )
                     &&
                     tsrange(
                        b.booking_date + b.booking_time,
                        (b.booking_date + b.booking_time)
                            + make_interval(
                                mins => b.duration_minutes
                              ),
                        '[)'
                     )
                ORDER BY a.id, b.id
                LIMIT 50
                """
            )
        ).mappings()
    )


def _constraint_exists(
    connection,
    constraint_name: str,
) -> bool:
    return (
        connection.scalar(
            text(
                """
                SELECT 1
                FROM pg_constraint
                WHERE conname = :constraint_name
                  AND conrelid = 'bookings'::regclass
                LIMIT 1
                """
            ),
            {
                "constraint_name": constraint_name,
            },
        )
        is not None
    )


def upgrade_booking_overlap_exclusion() -> None:
    """
    Запрещает пересечение активных Booking на уровне PostgreSQL.

    Для status IN ('new', 'confirmed') запрещаются пересечения:
    - у одного master_id;
    - у одного client_id.

    Используется EXCLUDE USING gist и расширение btree_gist.
    Исторические completed/cancelled записи ограничения не блокируют.
    """
    inspector = inspect(engine)

    if "bookings" not in inspector.get_table_names():
        logger.info(
            "Таблица bookings ещё не создана. "
            "Overlap exclusion upgrade пропущен."
        )
        return

    if engine.dialect.name != "postgresql":
        logger.info(
            "Booking overlap exclusion upgrade пропущен для %s.",
            engine.dialect.name,
        )
        return

    required_columns = {
        "id",
        "client_id",
        "master_id",
        "booking_date",
        "booking_time",
        "duration_minutes",
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
            "Нельзя включить overlap exclusion для Booking: "
            "отсутствуют поля "
            + ", ".join(missing_columns)
        )

    with engine.begin() as connection:
        master_overlaps = _overlap_pairs(
            connection,
            "master_id",
        )
        client_overlaps = _overlap_pairs(
            connection,
            "client_id",
        )

        problems = []

        if master_overlaps:
            problems.append(
                "мастер: "
                + "; ".join(
                    (
                        f"owner={row['owner_id']} "
                        f"Booking.id="
                        f"{row['booking_a_id']}/"
                        f"{row['booking_b_id']}"
                    )
                    for row in master_overlaps
                )
            )

        if client_overlaps:
            problems.append(
                "клиент: "
                + "; ".join(
                    (
                        f"owner={row['owner_id']} "
                        f"Booking.id="
                        f"{row['booking_a_id']}/"
                        f"{row['booking_b_id']}"
                    )
                    for row in client_overlaps
                )
            )

        if problems:
            raise RuntimeError(
                "Нельзя включить DB-защиту от пересечений Booking: "
                "в старой базе уже есть активные пересечения. "
                + " | ".join(problems)
                + ". Исправьте записи вручную и повторите запуск."
            )

        try:
            connection.execute(
                text(
                    """
                    CREATE EXTENSION IF NOT EXISTS btree_gist
                    """
                )
            )
        except DBAPIError as exc:
            raise RuntimeError(
                "PostgreSQL не разрешил включить расширение "
                "btree_gist, необходимое для защиты интервалов "
                "Booking. Разрешите btree_gist в базе и "
                "повторите запуск."
            ) from exc

        if not _constraint_exists(
            connection,
            "ex_bookings_active_master_overlap",
        ):
            connection.execute(
                text(
                    """
                    ALTER TABLE bookings
                    ADD CONSTRAINT
                        ex_bookings_active_master_overlap
                    EXCLUDE USING gist (
                        master_id WITH =,
                        tsrange(
                            booking_date + booking_time,
                            (booking_date + booking_time)
                                + make_interval(
                                    mins => duration_minutes
                                  ),
                            '[)'
                        ) WITH &&
                    )
                    WHERE (
                        status IN ('new', 'confirmed')
                    )
                    """
                )
            )

        if not _constraint_exists(
            connection,
            "ex_bookings_active_client_overlap",
        ):
            connection.execute(
                text(
                    """
                    ALTER TABLE bookings
                    ADD CONSTRAINT
                        ex_bookings_active_client_overlap
                    EXCLUDE USING gist (
                        client_id WITH =,
                        tsrange(
                            booking_date + booking_time,
                            (booking_date + booking_time)
                                + make_interval(
                                    mins => duration_minutes
                                  ),
                            '[)'
                        ) WITH &&
                    )
                    WHERE (
                        status IN ('new', 'confirmed')
                    )
                    """
                )
            )

    logger.info(
        "Booking overlap exclusion включён "
        "для мастеров и клиентов."
    )
