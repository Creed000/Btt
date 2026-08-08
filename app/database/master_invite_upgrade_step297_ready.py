import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)


def upgrade_master_invites() -> None:
    """
    Гарантирует только одно pending-приглашение
    от одного салона одному пользователю.
    """
    inspector = inspect(engine)

    if "master_invites" not in inspector.get_table_names():
        logger.info(
            "Таблица master_invites пока отсутствует."
        )
        return

    dialect = engine.dialect.name

    with engine.begin() as connection:
        if dialect == "postgresql":
            connection.execute(
                text(
                    """
                    WITH ranked AS (
                        SELECT
                            id,
                            ROW_NUMBER() OVER (
                                PARTITION BY salon_id, invited_user_id
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
                          GROUP BY salon_id, invited_user_id
                      )
                    """
                )
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

    logger.info(
        "Таблица master_invites усилена."
    )
