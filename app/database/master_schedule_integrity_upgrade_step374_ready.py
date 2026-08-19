import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)
INDEX_NAME = "uq_master_schedule_master_weekday"


def _master_fk_rows(connection) -> list[dict]:
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
                  AND tc.table_name = 'master_schedules'
                  AND tc.constraint_type = 'FOREIGN KEY'
                  AND kcu.column_name = 'master_id'
                """
            )
        ).mappings()
    )


def _master_fk_is_correct(rows: list[dict]) -> bool:
    if len(rows) != 1:
        return False

    row = rows[0]
    return (
        row["target_table"] == "masters"
        and row["target_column"] == "id"
        and (row["delete_rule"] or "").upper() == "CASCADE"
    )


def upgrade_master_schedule_integrity() -> None:
    """
    Полная integrity-защита master_schedules.

    Гарантирует:
    - master_id/weekday/work_start/work_end/is_working NOT NULL;
    - weekday 0..6;
    - work_start < work_end;
    - одна строка на master_id + weekday;
    - master_id -> masters.id ON DELETE CASCADE;
    - DB defaults 09:00/18:00/true.

    Повреждённые данные автоматически не исправляются.
    """
    inspector = inspect(engine)

    if "master_schedules" not in inspector.get_table_names():
        return

    columns = {
        column["name"]
        for column in inspector.get_columns("master_schedules")
    }

    required = {
        "id",
        "master_id",
        "weekday",
        "work_start",
        "work_end",
        "is_working",
    }
    missing = required - columns

    if missing:
        raise RuntimeError(
            "Не удалось усилить master_schedules: отсутствуют колонки "
            + ", ".join(sorted(missing))
        )

    if engine.dialect.name not in {"postgresql", "sqlite"}:
        logger.warning(
            "Диалект %s не поддержан для master_schedules integrity.",
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
                    weekday,
                    work_start,
                    work_end,
                    is_working
                FROM master_schedules
                WHERE master_id IS NULL
                   OR weekday IS NULL
                   OR work_start IS NULL
                   OR work_end IS NULL
                   OR is_working IS NULL
                   OR weekday < 0
                   OR weekday > 6
                   OR work_start >= work_end
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
                    f"weekday={row['weekday']} "
                    f"time={row['work_start']}-{row['work_end']}"
                )
                for row in invalid
            )
            raise RuntimeError(
                "В master_schedules найдены некорректные строки. "
                + details
            )

        duplicates = connection.execute(
            text(
                """
                SELECT
                    master_id,
                    weekday,
                    array_agg(id ORDER BY id) AS schedule_ids
                FROM master_schedules
                GROUP BY master_id, weekday
                HAVING COUNT(*) > 1
                ORDER BY master_id, weekday
                LIMIT 50
                """
            )
        ).mappings().all() if engine.dialect.name == "postgresql" else []

        if duplicates:
            details = "; ".join(
                (
                    f"master_id={row['master_id']} "
                    f"weekday={row['weekday']} "
                    f"ids={list(row['schedule_ids'])}"
                )
                for row in duplicates
            )
            raise RuntimeError(
                "Нельзя включить уникальность расписания: "
                "найдены дубли master_id + weekday. "
                + details
            )

        if engine.dialect.name == "postgresql":
            orphan_ids = list(
                connection.execute(
                    text(
                        """
                        SELECT ms.id
                        FROM master_schedules AS ms
                        LEFT JOIN masters AS m
                          ON m.id = ms.master_id
                        WHERE m.id IS NULL
                        ORDER BY ms.id
                        LIMIT 50
                        """
                    )
                ).scalars()
            )

            if orphan_ids:
                raise RuntimeError(
                    "Нельзя включить FK master_schedules.master_id: "
                    "найдены сиротские id="
                    + ", ".join(str(item) for item in orphan_ids)
                )

            for column_name in (
                "master_id",
                "weekday",
                "work_start",
                "work_end",
                "is_working",
            ):
                connection.execute(
                    text(
                        f"ALTER TABLE master_schedules "
                        f"ALTER COLUMN {column_name} SET NOT NULL"
                    )
                )

            connection.execute(
                text(
                    "ALTER TABLE master_schedules "
                    "ALTER COLUMN work_start SET DEFAULT '09:00:00'"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE master_schedules "
                    "ALTER COLUMN work_end SET DEFAULT '18:00:00'"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE master_schedules "
                    "ALTER COLUMN is_working SET DEFAULT true"
                )
            )

            for name in (
                "ck_master_schedules_weekday_range",
                "ck_master_schedules_work_time_order",
            ):
                connection.execute(
                    text(
                        f"ALTER TABLE master_schedules "
                        f"DROP CONSTRAINT IF EXISTS {name}"
                    )
                )

            connection.execute(
                text(
                    """
                    ALTER TABLE master_schedules
                    ADD CONSTRAINT ck_master_schedules_weekday_range
                    CHECK (weekday BETWEEN 0 AND 6)
                    """
                )
            )
            connection.execute(
                text(
                    """
                    ALTER TABLE master_schedules
                    ADD CONSTRAINT ck_master_schedules_work_time_order
                    CHECK (work_start < work_end)
                    """
                )
            )

            current_fks = _master_fk_rows(connection)
            if not _master_fk_is_correct(current_fks):
                for fk in current_fks:
                    safe_name = fk["constraint_name"].replace('"', '""')
                    connection.execute(
                        text(
                            f'ALTER TABLE master_schedules '
                            f'DROP CONSTRAINT IF EXISTS "{safe_name}"'
                        )
                    )

                connection.execute(
                    text(
                        """
                        ALTER TABLE master_schedules
                        ADD CONSTRAINT fk_master_schedules_master_id
                        FOREIGN KEY (master_id)
                        REFERENCES masters (id)
                        ON DELETE CASCADE
                        """
                    )
                )

        connection.execute(
            text(
                f"""
                CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_NAME}
                ON master_schedules (master_id, weekday)
                """
            )
        )

    logger.info(
        "Полная integrity-защита master_schedules включена."
    )
