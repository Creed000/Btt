import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)


CORE_COLUMNS = (
    "user_id",
    "rating",
    "booking_enabled",
    "is_verified",
)


def _foreign_keys_for_user(
    connection,
) -> list[dict]:
    return list(
        connection.execute(
            text(
                """
                SELECT
                    tc.constraint_name,
                    ccu.table_name AS target_table,
                    ccu.column_name AS target_column,
                    rc.delete_rule
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.constraint_schema = kcu.constraint_schema
                JOIN information_schema.constraint_column_usage AS ccu
                  ON tc.constraint_name = ccu.constraint_name
                 AND tc.constraint_schema = ccu.constraint_schema
                JOIN information_schema.referential_constraints AS rc
                  ON tc.constraint_name = rc.constraint_name
                 AND tc.constraint_schema = rc.constraint_schema
                WHERE tc.table_schema = current_schema()
                  AND tc.table_name = 'masters'
                  AND tc.constraint_type = 'FOREIGN KEY'
                  AND kcu.column_name = 'user_id'
                """
            )
        ).mappings()
    )


def _user_fk_is_correct(
    rows: list[dict],
) -> bool:
    if len(rows) != 1:
        return False

    row = rows[0]

    return (
        row["target_table"] == "users"
        and row["target_column"] == "id"
        and (row["delete_rule"] or "").upper()
        in {"RESTRICT", "NO ACTION"}
    )


def upgrade_master_core_integrity() -> None:
    """
    Укрепляет существующую таблицу masters.

    Гарантирует:
    - user_id/rating/booking_enabled/is_verified NOT NULL;
    - один Master на один User;
    - user_id -> users.id ON DELETE RESTRICT;
    - rating в диапазоне 0..5.

    Повреждённые данные автоматически не исправляются.
    """
    inspector = inspect(engine)

    if "masters" not in inspector.get_table_names():
        logger.info(
            "Таблица masters ещё не создана. "
            "Master core integrity upgrade пропущен."
        )
        return

    if engine.dialect.name != "postgresql":
        logger.info(
            "Master core integrity upgrade пропущен для %s.",
            engine.dialect.name,
        )
        return

    tables = set(
        inspector.get_table_names()
    )

    if "users" not in tables:
        raise RuntimeError(
            "Нельзя включить Master core integrity: "
            "таблица users отсутствует."
        )

    columns = {
        column["name"]
        for column in inspector.get_columns(
            "masters"
        )
    }

    missing_columns = [
        name
        for name in CORE_COLUMNS
        if name not in columns
    ]

    if missing_columns:
        raise RuntimeError(
            "В masters отсутствуют обязательные поля: "
            + ", ".join(missing_columns)
        )

    with engine.begin() as connection:
        broken = list(
            connection.execute(
                text(
                    """
                    SELECT
                        id,
                        user_id,
                        rating,
                        booking_enabled,
                        is_verified
                    FROM masters
                    WHERE user_id IS NULL
                       OR rating IS NULL
                       OR booking_enabled IS NULL
                       OR is_verified IS NULL
                       OR rating < 0
                       OR rating > 5
                    ORDER BY id
                    LIMIT 50
                    """
                )
            ).mappings()
        )

        if broken:
            details = "; ".join(
                (
                    f"id={row['id']} "
                    f"user_id={row['user_id']} "
                    f"rating={row['rating']}"
                )
                for row in broken
            )

            raise RuntimeError(
                "Нельзя включить Master core integrity: "
                "найдены NULL/некорректные значения. "
                + details
            )

        duplicate_users = list(
            connection.execute(
                text(
                    """
                    SELECT
                        user_id,
                        array_agg(id ORDER BY id) AS master_ids
                    FROM masters
                    GROUP BY user_id
                    HAVING COUNT(*) > 1
                    ORDER BY user_id
                    LIMIT 50
                    """
                )
            ).mappings()
        )

        if duplicate_users:
            details = "; ".join(
                (
                    f"user_id={row['user_id']} "
                    f"Master.id={list(row['master_ids'])}"
                )
                for row in duplicate_users
            )

            raise RuntimeError(
                "Нельзя включить уникальность Master.user_id: "
                "найдены дубли. "
                + details
            )

        orphan_ids = list(
            connection.execute(
                text(
                    """
                    SELECT m.id
                    FROM masters AS m
                    LEFT JOIN users AS u
                      ON u.id = m.user_id
                    WHERE u.id IS NULL
                    ORDER BY m.id
                    LIMIT 50
                    """
                )
            ).scalars()
        )

        if orphan_ids:
            raise RuntimeError(
                "Нельзя включить FK masters.user_id: "
                "найдены сиротские Master.id="
                + ", ".join(
                    str(item)
                    for item in orphan_ids
                )
            )

        for column_name in CORE_COLUMNS:
            connection.execute(
                text(
                    f"""
                    ALTER TABLE masters
                    ALTER COLUMN {column_name} SET NOT NULL
                    """
                )
            )

        connection.execute(
            text(
                """
                ALTER TABLE masters
                DROP CONSTRAINT IF EXISTS
                    ck_masters_rating_range
                """
            )
        )

        connection.execute(
            text(
                """
                ALTER TABLE masters
                ADD CONSTRAINT ck_masters_rating_range
                CHECK (rating BETWEEN 0 AND 5)
                """
            )
        )

        connection.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                    uq_masters_user_id
                ON masters (user_id)
                """
            )
        )

        current_fks = _foreign_keys_for_user(
            connection
        )

        if not _user_fk_is_correct(
            current_fks
        ):
            for fk in current_fks:
                safe_name = fk[
                    "constraint_name"
                ].replace('"', '""')

                connection.execute(
                    text(
                        f'ALTER TABLE masters '
                        f'DROP CONSTRAINT IF EXISTS '
                        f'"{safe_name}"'
                    )
                )

            connection.execute(
                text(
                    """
                    ALTER TABLE masters
                    ADD CONSTRAINT fk_masters_user_id
                    FOREIGN KEY (user_id)
                    REFERENCES users (id)
                    ON DELETE RESTRICT
                    """
                )
            )

    logger.info(
        "Master core integrity включена."
    )
