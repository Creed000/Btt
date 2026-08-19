import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)


VALID_STATUSES = (
    "pending",
    "accepted",
    "declined",
    "expired",
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
                  AND tc.table_name = 'master_invites'
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


def upgrade_master_invites() -> None:
    """
    Полная integrity-защита master_invites.

    Гарантирует:
    - salon_id/invited_user_id/invited_by_user_id/status/created_at NOT NULL;
    - допустимые статусы;
    - pending => resolved_at IS NULL;
    - terminal/replaced => resolved_at IS NOT NULL;
    - одно pending-приглашение на salon + invited_user;
    - все исторические FK работают через ON DELETE RESTRICT.

    Старые дубли pending, как и раньше, переводятся в replaced.
    """
    inspector = inspect(engine)

    if "master_invites" not in inspector.get_table_names():
        logger.info(
            "Таблица master_invites пока отсутствует."
        )
        return

    dialect = engine.dialect.name

    required = {
        "id",
        "salon_id",
        "invited_user_id",
        "invited_by_user_id",
        "status",
        "created_at",
        "resolved_at",
    }

    columns = {
        column["name"]
        for column in inspector.get_columns("master_invites")
    }

    missing = sorted(required - columns)
    if missing:
        raise RuntimeError(
            "В master_invites отсутствуют обязательные поля: "
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
                                PARTITION BY
                                    salon_id,
                                    invited_user_id
                                ORDER BY id DESC
                            ) AS rn
                        FROM master_invites
                        WHERE status = 'pending'
                    )
                    UPDATE master_invites AS i
                    SET status = 'replaced',
                        resolved_at = COALESCE(
                            i.resolved_at,
                            CURRENT_TIMESTAMP
                        )
                    FROM ranked
                    WHERE i.id = ranked.id
                      AND ranked.rn > 1
                    """
                )
            )

        elif dialect == "sqlite":
            connection.execute(
                text(
                    """
                    UPDATE master_invites
                    SET status = 'replaced',
                        resolved_at = COALESCE(
                            resolved_at,
                            CURRENT_TIMESTAMP
                        )
                    WHERE status = 'pending'
                      AND id NOT IN (
                          SELECT MAX(id)
                          FROM master_invites
                          WHERE status = 'pending'
                          GROUP BY
                              salon_id,
                              invited_user_id
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
                        invited_user_id,
                        invited_by_user_id,
                        status,
                        created_at,
                        resolved_at
                    FROM master_invites
                    WHERE salon_id IS NULL
                       OR invited_user_id IS NULL
                       OR invited_by_user_id IS NULL
                       OR status IS NULL
                       OR status NOT IN (
                            'pending',
                            'accepted',
                            'declined',
                            'expired',
                            'replaced'
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
                    f"status={row['status']!r} "
                    f"resolved_at={row['resolved_at']!r}"
                )
                for row in invalid
            )
            raise RuntimeError(
                "Нельзя включить integrity master_invites: "
                "найдены некорректные строки. "
                + details
            )

        connection.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                    ux_master_invites_one_pending
                ON master_invites (
                    salon_id,
                    invited_user_id
                )
                WHERE status = 'pending'
                """
            )
        )

        connection.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS
                    ix_master_invites_user_status
                ON master_invites (
                    invited_user_id,
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
                        "Нельзя включить FK master_invites: "
                        f"таблица {required_table} отсутствует."
                    )

            orphan_checks = (
                ("salon_id", "salons"),
                ("invited_user_id", "users"),
                ("invited_by_user_id", "users"),
            )

            for column_name, target_table in orphan_checks:
                orphan_ids = list(
                    connection.execute(
                        text(
                            f"""
                            SELECT child.id
                            FROM master_invites AS child
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
                        f"master_invites.{column_name}: "
                        "найдены сиротские id="
                        + ", ".join(
                            str(item)
                            for item in orphan_ids
                        )
                    )

            for column_name in (
                "salon_id",
                "invited_user_id",
                "invited_by_user_id",
                "status",
                "created_at",
            ):
                connection.execute(
                    text(
                        f"""
                        ALTER TABLE master_invites
                        ALTER COLUMN {column_name}
                        SET NOT NULL
                        """
                    )
                )

            connection.execute(
                text(
                    """
                    ALTER TABLE master_invites
                    ALTER COLUMN status
                    SET DEFAULT 'pending'
                    """
                )
            )

            connection.execute(
                text(
                    """
                    ALTER TABLE master_invites
                    ALTER COLUMN created_at
                    SET DEFAULT CURRENT_TIMESTAMP
                    """
                )
            )

            for constraint_name in (
                "ck_master_invites_status_valid",
                "ck_master_invites_resolved_state",
            ):
                connection.execute(
                    text(
                        f"""
                        ALTER TABLE master_invites
                        DROP CONSTRAINT IF EXISTS
                            {constraint_name}
                        """
                    )
                )

            connection.execute(
                text(
                    """
                    ALTER TABLE master_invites
                    ADD CONSTRAINT ck_master_invites_status_valid
                    CHECK (
                        status IN (
                            'pending',
                            'accepted',
                            'declined',
                            'expired',
                            'replaced'
                        )
                    )
                    """
                )
            )

            connection.execute(
                text(
                    """
                    ALTER TABLE master_invites
                    ADD CONSTRAINT ck_master_invites_resolved_state
                    CHECK (
                        (
                            status = 'pending'
                            AND resolved_at IS NULL
                        )
                        OR
                        (
                            status <> 'pending'
                            AND resolved_at IS NOT NULL
                        )
                    )
                    """
                )
            )

            fk_specs = (
                (
                    "salon_id",
                    "salons",
                    "fk_master_invites_salon_id",
                ),
                (
                    "invited_user_id",
                    "users",
                    "fk_master_invites_invited_user_id",
                ),
                (
                    "invited_by_user_id",
                    "users",
                    "fk_master_invites_invited_by_user_id",
                ),
            )

            for (
                column_name,
                target_table,
                constraint_name,
            ) in fk_specs:
                rows = _foreign_keys_for_column(
                    connection,
                    column_name,
                )

                if _fk_is_restrict(
                    rows,
                    target_table,
                ):
                    continue

                for row in rows:
                    safe_name = row[
                        "constraint_name"
                    ].replace('"', '""')

                    connection.execute(
                        text(
                            f'ALTER TABLE master_invites '
                            f'DROP CONSTRAINT IF EXISTS '
                            f'"{safe_name}"'
                        )
                    )

                connection.execute(
                    text(
                        f"""
                        ALTER TABLE master_invites
                        ADD CONSTRAINT {constraint_name}
                        FOREIGN KEY ({column_name})
                        REFERENCES {target_table} (id)
                        ON DELETE RESTRICT
                        """
                    )
                )

    logger.info(
        "Полная integrity-защита master_invites включена."
    )
