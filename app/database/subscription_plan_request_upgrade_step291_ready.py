import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)


def upgrade_subscription_plan_requests() -> None:
    """
    Идемпотентно усиливает таблицу запросов тарифов.

    Гарантия:
    у одного салона может существовать только
    один запрос со status='pending'.

    Перед созданием уникального partial index
    старые дубли автоматически переводятся
    в status='replaced', оставляя pending
    только самый новый запрос.
    """
    inspector = inspect(engine)

    if (
        "subscription_plan_requests"
        not in inspector.get_table_names()
    ):
        # Таблица будет создана через Base.metadata.create_all().
        # На следующем старте upgrade применится повторно.
        logger.info(
            "Таблица subscription_plan_requests "
            "пока отсутствует."
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

    logger.info(
        "Таблица subscription_plan_requests усилена."
    )
