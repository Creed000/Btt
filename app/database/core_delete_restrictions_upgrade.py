import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)


FK_RULES = (
    {
        "table": "bookings",
        "column": "client_id",
        "target_table": "users",
        "constraint_name": "fk_bookings_client_id",
    },
    {
        "table": "bookings",
        "column": "master_id",
        "target_table": "masters",
        "constraint_name": "fk_bookings_master_id",
    },
    {
        "table": "masters",
        "column": "user_id",
        "target_table": "users",
        "constraint_name": "fk_masters_user_id",
    },
    {
        "table": "salons",
        "column": "owner_id",
        "target_table": "users",
        "constraint_name": "fk_salons_owner_id",
    },
)


def _foreign_keys_for_column(
    connection,
    table_name: str,
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
                  AND tc.table_name = :table_name
                  AND tc.constraint_type = 'FOREIGN KEY'
                  AND kcu.column_name = :column_name
                """
            ),
            {
                "table_name": table_name,
                "column_name": column_name,
            },
        ).mappings()
    )


def _fk_is_restrict(
    rows: list[dict],
    target_table: str,
) -> bool:
    if len(rows) != 1:
        return False

    row = rows[0]
    delete_rule = (row["delete_rule"] or "").upper()

    return (
        row["target_table"] == target_table
        and row["target_column"] == "id"
        and delete_rule in {"RESTRICT", "NO ACTION"}
    )


def _orphan_ids(
    connection,
    table_name: str,
    column_name: str,
    target_table: str,
) -> list[int]:
    return list(
        connection.execute(
            text(
                f"""
                SELECT child.id
                FROM {table_name} AS child
                LEFT JOIN {target_table} AS parent
                  ON parent.id = child.{column_name}
                WHERE child.{column_name} IS NOT NULL
                  AND parent.id IS NULL
                ORDER BY child.id
                LIMIT 50
                """
            )
        ).scalars()
    )


def upgrade_core_delete_restrictions() -> None:
    """
    Переводит основные исторические связи SaaS на ON DELETE RESTRICT.

    Защищаются:
    bookings.client_id -> users.id
    bookings.master_id -> masters.id
    masters.user_id -> users.id
    salons.owner_id -> users.id

    Это блокирует прямое физическое удаление User/Master,
    если оно уничтожило бы основную историю бизнеса.
    """
    if engine.dialect.name != "postgresql":
        logger.info(
            "Core delete restriction upgrade пропущен для %s.",
            engine.dialect.name,
        )
        return

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    with engine.begin() as connection:
        for rule in FK_RULES:
            table_name = rule["table"]
            target_table = rule["target_table"]
            column_name = rule["column"]

            if (
                table_name not in tables
                or target_table not in tables
            ):
                logger.info(
                    "FK %s.%s пропущен: таблицы ещё не созданы.",
                    table_name,
                    column_name,
                )
                continue

            columns = {
                column["name"]
                for column in inspect(connection).get_columns(
                    table_name
                )
            }

            if column_name not in columns:
                raise RuntimeError(
                    f"В {table_name} отсутствует обязательная "
                    f"колонка {column_name}."
                )

            orphan_ids = _orphan_ids(
                connection,
                table_name,
                column_name,
                target_table,
            )

            if orphan_ids:
                raise RuntimeError(
                    f"Нельзя включить RESTRICT для "
                    f"{table_name}.{column_name}: "
                    f"найдены сиротские строки id="
                    + ", ".join(str(item) for item in orphan_ids)
                )

            current_fks = _foreign_keys_for_column(
                connection,
                table_name,
                column_name,
            )

            if _fk_is_restrict(
                current_fks,
                target_table,
            ):
                continue

            for fk in current_fks:
                name = fk["constraint_name"]
                safe_name = name.replace('"', '""')

                connection.execute(
                    text(
                        f'ALTER TABLE {table_name} '
                        f'DROP CONSTRAINT IF EXISTS "{safe_name}"'
                    )
                )

            connection.execute(
                text(
                    f"""
                    ALTER TABLE {table_name}
                    ADD CONSTRAINT {rule['constraint_name']}
                    FOREIGN KEY ({column_name})
                    REFERENCES {target_table} (id)
                    ON DELETE RESTRICT
                    """
                )
            )

    logger.info(
        "Core delete restrictions включены."
    )
