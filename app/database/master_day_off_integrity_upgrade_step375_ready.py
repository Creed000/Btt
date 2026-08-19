import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)
INDEX_NAME = "uq_master_days_off_master_date"


def _master_fk_rows(
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
                  AND tc.table_name = 'master_days_off'
                  AND tc.constraint_type = 'FOREIGN KEY'
                  AND kcu.column_name = 'master_id'
                """
            )
        ).mappings()
    )


def _master_fk_is_correct(
    rows: list[dict],
) -> bool:
    if len(rows) != 1:
        return False

    row = rows[0]

    return (
        row["target_table"] == "masters"
        and row["target_column"] == "id"
        and (row["delete_rule"] or "").upper()
        == "CASCADE"
    )


def upgrade_master_day_off_integrity() -> None:
    """
    Полная integrity-защита master_days_off.

    Гарантирует:
    - master_id/day_off_date NOT NULL;
    - одна строка на master_id + day_off_date;
    - master_id -> masters.id ON DELETE CASCADE;
    - отсутствие сиротских строк.

    reason остаётся nullable намеренно.
    """
    inspector = inspect(engine)

    if "master_days_off" not in inspector.get_table_names():
        return

    columns = {
        column["name"]
        for column in inspector.get_columns(
            "master_days_off"
        )
    }

    required = {
        "id",
        "master_id",
        "day_off_date",
    }

    missing = required - columns

    if missing:
        raise RuntimeError(
            "Не удалось усилить master_days_off: "
            "отсутствуют колонки "
            + ", ".join(sorted(missing))
        )

    if engine.dialect.name not in {
        "postgresql",
        "sqlite",
    }:
        logger.warning(
            "Диалект %s не поддержан для "
            "master_days_off integrity.",
            engine.dialect.name,
        )
        return

    with engine.begin() as connection:
        invalid = connection.execute(
            text(
                """
                SELECT
                    id,
                    master_id,
                    day_off_date
                FROM master_days_off
                WHERE master_id IS NULL
                   OR day_off_date IS NULL
                ORDER BY id
                LIMIT 50
                """
            )
        ).mappings().all()

        if invalid:
            details = "; ".join(
                (
                    f"id={row['id']} "
                    f"master_id={row['master_id']} "
                    f"date={row['day_off_date']}"
                )
                for row in invalid
            )

            raise RuntimeError(
                "В master_days_off найдены NULL "
                "в обязательных полях. "
                + details
            )

        duplicates = connection.execute(
            text(
                """
                SELECT
                    master_id,
                    day_off_date,
                    COUNT(*) AS duplicate_count
                FROM master_days_off
                GROUP BY master_id, day_off_date
                HAVING COUNT(*) > 1
                ORDER BY master_id, day_off_date
                LIMIT 50
                """
            )
        ).all()

        if duplicates:
            details = "; ".join(
                (
                    f"master_id={row.master_id}, "
                    f"date={row.day_off_date}, "
                    f"count={row.duplicate_count}"
                )
                for row in duplicates
            )

            raise RuntimeError(
                "Нельзя включить уникальность "
                "выходных дат: в БД уже есть "
                "дубли master_id + day_off_date. "
                f"Найдены: {details}"
            )

        if engine.dialect.name == "postgresql":
            if "masters" not in inspect(
                connection
            ).get_table_names():
                raise RuntimeError(
                    "Нельзя включить FK "
                    "master_days_off.master_id: "
                    "таблица masters отсутствует."
                )

            orphan_ids = list(
                connection.execute(
                    text(
                        """
                        SELECT d.id
                        FROM master_days_off AS d
                        LEFT JOIN masters AS m
                          ON m.id = d.master_id
                        WHERE m.id IS NULL
                        ORDER BY d.id
                        LIMIT 50
                        """
                    )
                ).scalars()
            )

            if orphan_ids:
                raise RuntimeError(
                    "Нельзя включить FK "
                    "master_days_off.master_id: "
                    "найдены сиротские id="
                    + ", ".join(
                        str(item)
                        for item in orphan_ids
                    )
                )

            connection.execute(
                text(
                    """
                    ALTER TABLE master_days_off
                    ALTER COLUMN master_id
                    SET NOT NULL
                    """
                )
            )

            connection.execute(
                text(
                    """
                    ALTER TABLE master_days_off
                    ALTER COLUMN day_off_date
                    SET NOT NULL
                    """
                )
            )

            current_fks = _master_fk_rows(
                connection
            )

            if not _master_fk_is_correct(
                current_fks
            ):
                for fk in current_fks:
                    safe_name = fk[
                        "constraint_name"
                    ].replace('"', '""')

                    connection.execute(
                        text(
                            f'ALTER TABLE master_days_off '
                            f'DROP CONSTRAINT IF EXISTS '
                            f'"{safe_name}"'
                        )
                    )

                connection.execute(
                    text(
                        """
                        ALTER TABLE master_days_off
                        ADD CONSTRAINT
                            fk_master_days_off_master_id
                        FOREIGN KEY (master_id)
                        REFERENCES masters (id)
                        ON DELETE CASCADE
                        """
                    )
                )

        connection.execute(
            text(
                f"""
                CREATE UNIQUE INDEX IF NOT EXISTS
                    {INDEX_NAME}
                ON master_days_off (
                    master_id,
                    day_off_date
                )
                """
            )
        )

    logger.info(
        "Полная integrity-защита "
        "master_days_off включена."
    )
