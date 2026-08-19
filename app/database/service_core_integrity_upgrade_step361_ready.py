import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)


CORE_COLUMNS = (
    "master_id",
    "category_id",
    "title",
    "duration",
    "price",
)


FOREIGN_KEYS = {
    "master_id": {
        "target_table": "masters",
        "constraint_name": "fk_services_master_id",
    },
    "category_id": {
        "target_table": "categories",
        "constraint_name": "fk_services_category_id",
    },
}


def _orphan_ids(
    connection,
    column_name: str,
    target_table: str,
) -> list[int]:
    return list(
        connection.execute(
            text(
                f"""
                SELECT s.id
                FROM services AS s
                LEFT JOIN {target_table} AS target
                  ON target.id = s.{column_name}
                WHERE s.{column_name} IS NOT NULL
                  AND target.id IS NULL
                ORDER BY s.id
                LIMIT 50
                """
            )
        ).scalars()
    )


def _foreign_keys_for_column(
    connection,
    column_name: str,
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
                  AND tc.table_name = 'services'
                  AND tc.constraint_type = 'FOREIGN KEY'
                  AND kcu.column_name = :column_name
                """
            ),
            {"column_name": column_name},
        ).mappings()
    )


def _fk_is_correct(
    rows: list[dict],
    target_table: str,
) -> bool:
    if len(rows) != 1:
        return False

    row = rows[0]
    return (
        row["target_table"] == target_table
        and row["target_column"] == "id"
        and (row["delete_rule"] or "").upper()
            in {"NO ACTION", "RESTRICT"}
    )


def upgrade_service_core_integrity() -> None:
    """
    Укрепляет существующую таблицу services в PostgreSQL.

    Гарантирует:
    - master_id/category_id/title/duration/price NOT NULL;
    - title не пустой после TRIM;
    - master_id ссылается на masters.id;
    - category_id ссылается на categories.id.

    Повреждённые данные не исправляются автоматически.
    """
    inspector = inspect(engine)

    if "services" not in inspector.get_table_names():
        logger.info(
            "Таблица services ещё не создана. "
            "Service core integrity upgrade пропущен."
        )
        return

    if engine.dialect.name != "postgresql":
        logger.info(
            "Service core integrity upgrade пропущен для %s.",
            engine.dialect.name,
        )
        return

    tables = set(inspector.get_table_names())
    missing_tables = {"masters", "categories"} - tables
    if missing_tables:
        raise RuntimeError(
            "Нельзя включить Service core integrity: "
            "отсутствуют таблицы "
            + ", ".join(sorted(missing_tables))
        )

    columns = {
        column["name"]
        for column in inspector.get_columns("services")
    }
    missing_columns = [
        name for name in CORE_COLUMNS
        if name not in columns
    ]
    if missing_columns:
        raise RuntimeError(
            "В services отсутствуют обязательные колонки: "
            + ", ".join(missing_columns)
        )

    with engine.begin() as connection:
        broken = list(
            connection.execute(
                text(
                    """
                    SELECT
                        id,
                        master_id,
                        category_id,
                        title,
                        duration,
                        price
                    FROM services
                    WHERE master_id IS NULL
                       OR category_id IS NULL
                       OR title IS NULL
                       OR LENGTH(TRIM(title)) = 0
                       OR duration IS NULL
                       OR price IS NULL
                    ORDER BY id
                    LIMIT 50
                    """
                )
            ).mappings()
        )

        if broken:
            details = "; ".join(
                f"id={row['id']}"
                for row in broken
            )
            raise RuntimeError(
                "Нельзя включить обязательные поля Service: "
                "найдены NULL/пустые значения. "
                f"Первые строки: {details}. "
                "Исправьте данные вручную и повторите запуск."
            )

        orphan_messages = []
        for column_name, config in FOREIGN_KEYS.items():
            ids = _orphan_ids(
                connection,
                column_name,
                config["target_table"],
            )
            if ids:
                orphan_messages.append(
                    f"{column_name}: "
                    + ", ".join(str(item) for item in ids)
                )

        if orphan_messages:
            raise RuntimeError(
                "Нельзя включить FK Service: найдены сиротские ссылки. "
                + "; ".join(orphan_messages)
                + ". Исправьте данные вручную и повторите запуск."
            )

        for column_name in CORE_COLUMNS:
            connection.execute(
                text(
                    f"ALTER TABLE services "
                    f"ALTER COLUMN {column_name} SET NOT NULL"
                )
            )

        connection.execute(
            text(
                "ALTER TABLE services "
                "DROP CONSTRAINT IF EXISTS ck_services_title_not_blank"
            )
        )
        connection.execute(
            text(
                """
                ALTER TABLE services
                ADD CONSTRAINT ck_services_title_not_blank
                CHECK (LENGTH(TRIM(title)) > 0)
                """
            )
        )

        for column_name, config in FOREIGN_KEYS.items():
            rows = _foreign_keys_for_column(
                connection,
                column_name,
            )

            if _fk_is_correct(
                rows,
                config["target_table"],
            ):
                continue

            for row in rows:
                name = row["constraint_name"]
                safe_name = name.replace('"', '""')
                connection.execute(
                    text(
                        f'ALTER TABLE services '
                        f'DROP CONSTRAINT IF EXISTS "{safe_name}"'
                    )
                )

            connection.execute(
                text(
                    f"""
                    ALTER TABLE services
                    ADD CONSTRAINT {config['constraint_name']}
                    FOREIGN KEY ({column_name})
                    REFERENCES {config['target_table']} (id)
                    ON DELETE RESTRICT
                    """
                )
            )

    logger.info(
        "Service core integrity включена."
    )
