import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)


VALID_PLANS = (
    "free",
    "basic",
    "pro",
    "business",
)

VALID_STATUSES = (
    "pending",
    "approved",
    "rejected",
    "replaced",
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
                  AND tc.table_name = 'subscription_plan_requests'
                  AND tc.constraint_type = 'FOREIGN KEY'
                  AND kcu.column_name = :column_name
                """
            ),
            {"column_name": column_name},
        ).mappings()
    )


def _fk_is_restrict(
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
        in {"RESTRICT", "NO ACTION"}
    )


def upgrade_subscription_plan_requests() -> None:
    """
    Полная integrity-защита subscription_plan_requests.

    Гарантирует:
    - salon_id/requested_by_user_id/current_plan/requested_plan/
      status/created_at NOT NULL;
    - допустимые планы и статусы;
    - pending => resolved_at IS NULL;
    - approved/rejected/replaced => resolved_at IS NOT NULL;
    - один pending-запрос на один salon;
    - salon/user FK через ON DELETE RESTRICT.

    Старые дубли pending переводятся в replaced.
    """
    inspector = inspect(engine)

    if (
        "subscription_plan_requests"
        not in inspector.get_table_names()
    ):
        logger.info(
            "Таблица subscription_plan_requests пока отсутствует."
        )
        return

    dialect = engine.dialect.name

    required = {
        "id",
        "salon_id",
        "requested_by_user_id",
        "current_plan",
        "requested_plan",
        "status",
        "created_at",
        "resolved_at",
    }

    columns = {
        column["name"]
        for column in inspector.get_columns(
            "subscription_plan_requests"
        )
    }

    missing = sorted(required - columns)
    if missing:
        raise RuntimeError(
            "В subscription_plan_requests отсутствуют поля: "
            + ", ".join(missing)
        )

    with engine.begin() as connection:
        if dialect == "postgresql":
            connection.execute(
                text(
                    """
                    WITH ranked AS (
                        SELECT
                            id,
                            ROW_NUMBER() OVER (
                                PARTITION BY salon_id
                                ORDER BY id DESC
                            ) AS rn
                        FROM subscription_plan_requests
                        WHERE status = 'pending'
                    )
                    UPDATE subscription_plan_requests AS r
                    SET status = 'replaced',
                        resolved_at = COALESCE(
                            r.resolved_at,
                            CURRENT_TIMESTAMP
                        )
                    FROM ranked
                    WHERE r.id = ranked.id
                      AND ranked.rn > 1
                    """
                )
            )

        elif dialect == "sqlite":
            connection.execute(
                text(
                    """
                    UPDATE subscription_plan_requests
                    SET status = 'replaced',
                        resolved_at = COALESCE(
                            resolved_at,
                            CURRENT_TIMESTAMP
                        )
                    WHERE status = 'pending'
                      AND id NOT IN (
                          SELECT MAX(id)
                          FROM subscription_plan_requests
                          WHERE status = 'pending'
                          GROUP BY salon_id
                      )
                    """
                )
            )

        invalid = list(
            connection.execute(
                text(
                    """
                    SELECT
                        id,
                        salon_id,
                        requested_by_user_id,
                        current_plan,
                        requested_plan,
                        status,
                        created_at,
                        resolved_at
                    FROM subscription_plan_requests
                    WHERE salon_id IS NULL
                       OR requested_by_user_id IS NULL
                       OR current_plan IS NULL
                       OR current_plan NOT IN (
                            'free', 'basic', 'pro', 'business'
                       )
                       OR requested_plan IS NULL
                       OR requested_plan NOT IN (
                            'free', 'basic', 'pro', 'business'
                       )
                       OR status IS NULL
                       OR status NOT IN (
                            'pending', 'approved', 'rejected', 'replaced'
                       )
                       OR created_at IS NULL
                       OR (
                            status = 'pending'
                            AND resolved_at IS NOT NULL
                       )
                       OR (
                            status <> 'pending'
                            AND resolved_at IS NULL
                       )
                    ORDER BY id
                    LIMIT 50
                    """
                )
            ).mappings()
        )

        if invalid:
            details = "; ".join(
                (
                    f"id={row['id']} "
                    f"current={row['current_plan']!r} "
                    f"requested={row['requested_plan']!r} "
                    f"status={row['status']!r} "
                    f"resolved_at={row['resolved_at']!r}"
                )
                for row in invalid
            )
            raise RuntimeError(
                "Нельзя включить integrity запросов тарифа: "
                "найдены некорректные строки. "
                + details
            )

        connection.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                    ux_subscription_plan_requests_one_pending_per_salon
                ON subscription_plan_requests (salon_id)
                WHERE status = 'pending'
                """
            )
        )

        connection.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS
                    ix_subscription_plan_requests_status_created
                ON subscription_plan_requests (
                    status,
                    created_at
                )
                """
            )
        )

        if dialect == "postgresql":
            tables = set(
                inspect(connection).get_table_names()
            )

            for required_table in ("salons", "users"):
                if required_table not in tables:
                    raise RuntimeError(
                        "Нельзя включить FK запросов тарифа: "
                        f"таблица {required_table} отсутствует."
                    )

            orphan_specs = (
                ("salon_id", "salons"),
                ("requested_by_user_id", "users"),
            )

            for column_name, target_table in orphan_specs:
                orphan_ids = list(
                    connection.execute(
                        text(
                            f"""
                            SELECT child.id
                            FROM subscription_plan_requests AS child
                            LEFT JOIN {target_table} AS parent
                              ON parent.id = child.{column_name}
                            WHERE parent.id IS NULL
                            ORDER BY child.id
                            LIMIT 50
                            """
                        )
                    ).scalars()
                )

                if orphan_ids:
                    raise RuntimeError(
                        f"Нельзя включить FK "
                        f"subscription_plan_requests.{column_name}: "
                        "найдены сиротские id="
                        + ", ".join(str(item) for item in orphan_ids)
                    )

            for column_name in (
                "salon_id",
                "requested_by_user_id",
                "current_plan",
                "requested_plan",
                "status",
                "created_at",
            ):
                connection.execute(
                    text(
                        f"""
                        ALTER TABLE subscription_plan_requests
                        ALTER COLUMN {column_name} SET NOT NULL
                        """
                    )
                )

            connection.execute(
                text(
                    """
                    ALTER TABLE subscription_plan_requests
                    ALTER COLUMN status SET DEFAULT 'pending'
                    """
                )
            )
            connection.execute(
                text(
                    """
                    ALTER TABLE subscription_plan_requests
                    ALTER COLUMN created_at
                    SET DEFAULT CURRENT_TIMESTAMP
                    """
                )
            )

            constraints = {
                "ck_subscription_plan_requests_current_plan_valid":
                    "CHECK (current_plan IN "
                    "('free', 'basic', 'pro', 'business'))",
                "ck_subscription_plan_requests_requested_plan_valid":
                    "CHECK (requested_plan IN "
                    "('free', 'basic', 'pro', 'business'))",
                "ck_subscription_plan_requests_status_valid":
                    "CHECK (status IN "
                    "('pending', 'approved', 'rejected', 'replaced'))",
                "ck_subscription_plan_requests_resolved_state":
                    "CHECK ((status = 'pending' AND resolved_at IS NULL) "
                    "OR (status <> 'pending' AND resolved_at IS NOT NULL))",
            }

            for name, sql in constraints.items():
                connection.execute(
                    text(
                        f"ALTER TABLE subscription_plan_requests "
                        f"DROP CONSTRAINT IF EXISTS {name}"
                    )
                )
                connection.execute(
                    text(
                        f"ALTER TABLE subscription_plan_requests "
                        f"ADD CONSTRAINT {name} {sql}"
                    )
                )

            fk_specs = (
                (
                    "salon_id",
                    "salons",
                    "fk_subscription_plan_requests_salon_id",
                ),
                (
                    "requested_by_user_id",
                    "users",
                    "fk_subscription_plan_requests_requested_by_user_id",
                ),
            )

            for column_name, target_table, constraint_name in fk_specs:
                rows = _foreign_keys_for_column(
                    connection,
                    column_name,
                )

                if _fk_is_restrict(rows, target_table):
                    continue

                for row in rows:
                    safe_name = row[
                        "constraint_name"
                    ].replace('"', '""')
                    connection.execute(
                        text(
                            f'ALTER TABLE subscription_plan_requests '
                            f'DROP CONSTRAINT IF EXISTS "{safe_name}"'
                        )
                    )

                connection.execute(
                    text(
                        f"""
                        ALTER TABLE subscription_plan_requests
                        ADD CONSTRAINT {constraint_name}
                        FOREIGN KEY ({column_name})
                        REFERENCES {target_table} (id)
                        ON DELETE RESTRICT
                        """
                    )
                )

    logger.info(
        "Полная integrity-защита subscription_plan_requests включена."
    )
