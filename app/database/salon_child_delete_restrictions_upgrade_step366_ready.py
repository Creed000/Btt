import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)


SALON_CHILD_FKS = (
    {
        "table": "branches",
        "column": "salon_id",
        "constraint_name": "fk_branches_salon_id",
    },
    {
        "table": "master_salon_invites",
        "column": "salon_id",
        "constraint_name": "fk_master_salon_invites_salon_id",
    },
    {
        "table": "master_invites",
        "column": "salon_id",
        "constraint_name": "fk_master_invites_salon_id",
    },
    {
        "table": "subscription_plan_requests",
        "column": "salon_id",
        "constraint_name": "fk_subscription_plan_requests_salon_id",
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


def _is_restrict(rows: list[dict]) -> bool:
    if len(rows) != 1:
        return False

    row = rows[0]
    return (
        row["target_table"] == "salons"
        and row["target_column"] == "id"
        and (row["delete_rule"] or "").upper()
            in {"RESTRICT", "NO ACTION"}
    )


def upgrade_salon_child_delete_restrictions() -> None:
    """
    Запрещает физическое удаление Salon, если у него остаются
    филиалы или исторические invite/subscription-request строки.

    Обычная деактивация Salon и отвязка Master не затрагиваются.
    """
    if engine.dialect.name != "postgresql":
        logger.info(
            "Salon child delete restrictions пропущены для %s.",
            engine.dialect.name,
        )
        return

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    if "salons" not in tables:
        logger.info(
            "Таблица salons ещё не создана. Upgrade пропущен."
        )
        return

    with engine.begin() as connection:
        for rule in SALON_CHILD_FKS:
            table_name = rule["table"]
            column_name = rule["column"]

            if table_name not in tables:
                continue

            columns = {
                column["name"]
                for column in inspect(connection).get_columns(table_name)
            }

            if column_name not in columns:
                raise RuntimeError(
                    f"В {table_name} отсутствует {column_name}."
                )

            orphan_ids = list(
                connection.execute(
                    text(
                        f"""
                        SELECT child.id
                        FROM {table_name} AS child
                        LEFT JOIN salons AS salon
                          ON salon.id = child.{column_name}
                        WHERE child.{column_name} IS NOT NULL
                          AND salon.id IS NULL
                        ORDER BY child.id
                        LIMIT 50
                        """
                    )
                ).scalars()
            )

            if orphan_ids:
                raise RuntimeError(
                    f"Нельзя включить RESTRICT для {table_name}.{column_name}: "
                    "найдены сиротские строки id="
                    + ", ".join(str(item) for item in orphan_ids)
                )

            rows = _foreign_keys_for_column(
                connection,
                table_name,
                column_name,
            )

            if _is_restrict(rows):
                continue

            for row in rows:
                safe_name = row["constraint_name"].replace('"', '""')
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
                    REFERENCES salons (id)
                    ON DELETE RESTRICT
                    """
                )
            )

    logger.info(
        "Salon child delete restrictions включены."
    )
