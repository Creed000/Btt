import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)


def _user_fk_rows(connection) -> list[dict]:
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
                  AND tc.table_name = 'clients'
                  AND tc.constraint_type = 'FOREIGN KEY'
                  AND kcu.column_name = 'user_id'
                """
            )
        ).mappings()
    )


def _fk_is_restrict(rows: list[dict]) -> bool:
    if len(rows) != 1:
        return False

    row = rows[0]

    return (
        row["target_table"] == "users"
        and row["target_column"] == "id"
        and (row["delete_rule"] or "").upper()
        in {"RESTRICT", "NO ACTION"}
    )


def upgrade_client_core_integrity() -> None:
    """
    Укрепляет существующую таблицу clients.

    Гарантирует:
    - user_id/bonus_points/total_visits NOT NULL;
    - один Client на одного User;
    - bonus_points/total_visits неотрицательны;
    - user_id -> users.id ON DELETE RESTRICT.
    """
    inspector = inspect(engine)

    if "clients" not in inspector.get_table_names():
        logger.info(
            "Таблица clients ещё не создана. "
            "Client core integrity upgrade пропущен."
        )
        return

    if engine.dialect.name != "postgresql":
        logger.info(
            "Client core integrity upgrade пропущен для %s.",
            engine.dialect.name,
        )
        return

    tables = set(inspector.get_table_names())

    if "users" not in tables:
        raise RuntimeError(
            "Нельзя включить Client core integrity: "
            "таблица users отсутствует."
        )

    columns = {
        column["name"]
        for column in inspector.get_columns("clients")
    }

    required = {
        "user_id",
        "bonus_points",
        "total_visits",
    }

    missing = sorted(required - columns)

    if missing:
        raise RuntimeError(
            "В clients отсутствуют обязательные поля: "
            + ", ".join(missing)
        )

    with engine.begin() as connection:
        broken = list(
            connection.execute(
                text(
                    """
                    SELECT
                        id,
                        user_id,
                        bonus_points,
                        total_visits
                    FROM clients
                    WHERE user_id IS NULL
                       OR bonus_points IS NULL
                       OR total_visits IS NULL
                       OR bonus_points < 0
                       OR total_visits < 0
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
                    f"bonus={row['bonus_points']} "
                    f"visits={row['total_visits']}"
                )
                for row in broken
            )

            raise RuntimeError(
                "Нельзя включить Client core integrity: "
                "найдены NULL/отрицательные значения. "
                + details
            )

        duplicates = list(
            connection.execute(
                text(
                    """
                    SELECT
                        user_id,
                        array_agg(id ORDER BY id) AS client_ids
                    FROM clients
                    GROUP BY user_id
                    HAVING COUNT(*) > 1
                    ORDER BY user_id
                    LIMIT 50
                    """
                )
            ).mappings()
        )

        if duplicates:
            details = "; ".join(
                (
                    f"user_id={row['user_id']} "
                    f"Client.id={list(row['client_ids'])}"
                )
                for row in duplicates
            )

            raise RuntimeError(
                "Нельзя включить уникальность Client.user_id: "
                "найдены дубли. "
                + details
            )

        orphan_ids = list(
            connection.execute(
                text(
                    """
                    SELECT c.id
                    FROM clients AS c
                    LEFT JOIN users AS u
                      ON u.id = c.user_id
                    WHERE u.id IS NULL
                    ORDER BY c.id
                    LIMIT 50
                    """
                )
            ).scalars()
        )

        if orphan_ids:
            raise RuntimeError(
                "Нельзя включить FK clients.user_id: "
                "найдены сиротские Client.id="
                + ", ".join(
                    str(item)
                    for item in orphan_ids
                )
            )

        connection.execute(
            text(
                "ALTER TABLE clients "
                "ALTER COLUMN user_id SET NOT NULL"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE clients "
                "ALTER COLUMN bonus_points SET DEFAULT 0"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE clients "
                "ALTER COLUMN bonus_points SET NOT NULL"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE clients "
                "ALTER COLUMN total_visits SET DEFAULT 0"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE clients "
                "ALTER COLUMN total_visits SET NOT NULL"
            )
        )

        for name in (
            "ck_clients_bonus_points_nonnegative",
            "ck_clients_total_visits_nonnegative",
        ):
            connection.execute(
                text(
                    f"""
                    ALTER TABLE clients
                    DROP CONSTRAINT IF EXISTS {name}
                    """
                )
            )

        connection.execute(
            text(
                """
                ALTER TABLE clients
                ADD CONSTRAINT
                    ck_clients_bonus_points_nonnegative
                CHECK (bonus_points >= 0)
                """
            )
        )

        connection.execute(
            text(
                """
                ALTER TABLE clients
                ADD CONSTRAINT
                    ck_clients_total_visits_nonnegative
                CHECK (total_visits >= 0)
                """
            )
        )

        connection.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                    uq_clients_user_id
                ON clients (user_id)
                """
            )
        )

        current_fks = _user_fk_rows(
            connection
        )

        if not _fk_is_restrict(
            current_fks
        ):
            for fk in current_fks:
                safe_name = fk[
                    "constraint_name"
                ].replace('"', '""')

                connection.execute(
                    text(
                        f'ALTER TABLE clients '
                        f'DROP CONSTRAINT IF EXISTS '
                        f'"{safe_name}"'
                    )
                )

            connection.execute(
                text(
                    """
                    ALTER TABLE clients
                    ADD CONSTRAINT fk_clients_user_id
                    FOREIGN KEY (user_id)
                    REFERENCES users (id)
                    ON DELETE RESTRICT
                    """
                )
            )

    logger.info(
        "Client core integrity включена."
    )
