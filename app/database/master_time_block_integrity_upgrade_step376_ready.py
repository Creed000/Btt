import logging

from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError

from app.database.session import engine


logger = logging.getLogger(__name__)

INDEX_NAME = "ix_master_time_blocks_master_date"
EXCLUSION_NAME = "ex_master_time_blocks_no_overlap"


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
                  AND tc.table_name = 'master_time_blocks'
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
                  AND conrelid =
                      'master_time_blocks'::regclass
                LIMIT 1
                """
            ),
            {
                "constraint_name": constraint_name,
            },
        )
        is not None
    )


def upgrade_master_time_block_integrity() -> None:
    """
    Полная integrity-защита master_time_blocks.

    Гарантирует:
    - master_id/block_date/start_time/end_time NOT NULL;
    - start_time < end_time;
    - master_id -> masters.id ON DELETE CASCADE;
    - отсутствие пересекающихся блокировок одного мастера;
    - индекс master_id + block_date.

    Для PostgreSQL пересечения дополнительно запрещаются
    EXCLUDE USING gist.

    reason остаётся nullable намеренно.
    """
    inspector = inspect(engine)

    if (
        "master_time_blocks"
        not in inspector.get_table_names()
    ):
        return

    columns = {
        column["name"]
        for column in inspector.get_columns(
            "master_time_blocks"
        )
    }

    required = {
        "id",
        "master_id",
        "block_date",
        "start_time",
        "end_time",
    }

    missing = required - columns

    if missing:
        raise RuntimeError(
            "Не удалось усилить master_time_blocks: "
            "отсутствуют колонки "
            + ", ".join(sorted(missing))
        )

    if engine.dialect.name not in {
        "postgresql",
        "sqlite",
    }:
        logger.warning(
            "Диалект %s не поддержан для "
            "master_time_blocks integrity.",
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
                    block_date,
                    start_time,
                    end_time
                FROM master_time_blocks
                WHERE master_id IS NULL
                   OR block_date IS NULL
                   OR start_time IS NULL
                   OR end_time IS NULL
                   OR start_time >= end_time
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
                    f"date={row['block_date']} "
                    f"time={row['start_time']}-"
                    f"{row['end_time']}"
                )
                for row in invalid
            )

            raise RuntimeError(
                "В master_time_blocks найдены "
                "NULL/некорректные интервалы. "
                + details
            )

        overlaps = connection.execute(
            text(
                """
                SELECT
                    a.id AS first_id,
                    b.id AS second_id,
                    a.master_id,
                    a.block_date
                FROM master_time_blocks AS a
                JOIN master_time_blocks AS b
                  ON b.master_id = a.master_id
                 AND b.block_date = a.block_date
                 AND b.id > a.id
                 AND a.start_time < b.end_time
                 AND b.start_time < a.end_time
                ORDER BY
                    a.master_id,
                    a.block_date,
                    a.id,
                    b.id
                LIMIT 50
                """
            )
        ).mappings().all()

        if overlaps:
            details = "; ".join(
                (
                    f"master_id={row['master_id']} "
                    f"date={row['block_date']} "
                    f"blocks={row['first_id']}/"
                    f"{row['second_id']}"
                )
                for row in overlaps
            )

            raise RuntimeError(
                "В master_time_blocks найдены "
                "пересекающиеся блокировки. "
                + details
            )

        if engine.dialect.name == "postgresql":
            if (
                "masters"
                not in inspect(
                    connection
                ).get_table_names()
            ):
                raise RuntimeError(
                    "Нельзя включить FK "
                    "master_time_blocks.master_id: "
                    "таблица masters отсутствует."
                )

            orphan_ids = list(
                connection.execute(
                    text(
                        """
                        SELECT b.id
                        FROM master_time_blocks AS b
                        LEFT JOIN masters AS m
                          ON m.id = b.master_id
                        WHERE m.id IS NULL
                        ORDER BY b.id
                        LIMIT 50
                        """
                    )
                ).scalars()
            )

            if orphan_ids:
                raise RuntimeError(
                    "Нельзя включить FK "
                    "master_time_blocks.master_id: "
                    "найдены сиротские id="
                    + ", ".join(
                        str(item)
                        for item in orphan_ids
                    )
                )

            for column_name in (
                "master_id",
                "block_date",
                "start_time",
                "end_time",
            ):
                connection.execute(
                    text(
                        f"""
                        ALTER TABLE master_time_blocks
                        ALTER COLUMN {column_name}
                        SET NOT NULL
                        """
                    )
                )

            connection.execute(
                text(
                    """
                    ALTER TABLE master_time_blocks
                    DROP CONSTRAINT IF EXISTS
                        ck_master_time_blocks_time_order
                    """
                )
            )

            connection.execute(
                text(
                    """
                    ALTER TABLE master_time_blocks
                    ADD CONSTRAINT
                        ck_master_time_blocks_time_order
                    CHECK (start_time < end_time)
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
                            f'ALTER TABLE '
                            f'master_time_blocks '
                            f'DROP CONSTRAINT IF EXISTS '
                            f'"{safe_name}"'
                        )
                    )

                connection.execute(
                    text(
                        """
                        ALTER TABLE master_time_blocks
                        ADD CONSTRAINT
                            fk_master_time_blocks_master_id
                        FOREIGN KEY (master_id)
                        REFERENCES masters (id)
                        ON DELETE CASCADE
                        """
                    )
                )

            try:
                connection.execute(
                    text(
                        """
                        CREATE EXTENSION IF NOT EXISTS
                            btree_gist
                        """
                    )
                )
            except DBAPIError as exc:
                raise RuntimeError(
                    "PostgreSQL не разрешил включить "
                    "btree_gist, необходимый для защиты "
                    "MasterTimeBlock от пересечений."
                ) from exc

            if not _constraint_exists(
                connection,
                EXCLUSION_NAME,
            ):
                connection.execute(
                    text(
                        f"""
                        ALTER TABLE master_time_blocks
                        ADD CONSTRAINT {EXCLUSION_NAME}
                        EXCLUDE USING gist (
                            master_id WITH =,
                            tsrange(
                                block_date + start_time,
                                block_date + end_time,
                                '[)'
                            ) WITH &&
                        )
                        """
                    )
                )

        connection.execute(
            text(
                f"""
                CREATE INDEX IF NOT EXISTS
                    {INDEX_NAME}
                ON master_time_blocks (
                    master_id,
                    block_date
                )
                """
            )
        )

    logger.info(
        "Полная integrity-защита "
        "master_time_blocks включена."
    )
