import logging
from datetime import datetime, timedelta

from sqlalchemy import inspect, text

from app.database.base import Base
from app.database.session import engine

# Импорт моделей нужен, чтобы Base.metadata знал обо всех таблицах.
import app.models  # noqa: F401


logger = logging.getLogger(__name__)


def _column_names(table_name: str) -> set[str]:
    inspector = inspect(engine)

    if table_name not in inspector.get_table_names():
        return set()

    return {
        column["name"]
        for column in inspector.get_columns(table_name)
    }


def upgrade_database_schema() -> None:
    """
    Безопасно создаёт отсутствующие таблицы и добавляет SaaS-поля
    в существующую таблицу salons.

    Функция идемпотентна: её можно запускать при каждом старте.
    """
    Base.metadata.create_all(bind=engine)

    salon_columns = _column_names("salons")

    if not salon_columns:
        logger.info("Таблица salons создана с актуальной схемой.")
        return

    dialect = engine.dialect.name

    with engine.begin() as connection:
        def add_column_if_missing(
            column_name: str,
            postgres_sql: str,
            sqlite_sql: str | None = None,
        ) -> None:
            if column_name in salon_columns:
                return

            sql = (
                sqlite_sql
                if dialect == "sqlite" and sqlite_sql is not None
                else postgres_sql
            )

            connection.execute(text(sql))
            salon_columns.add(column_name)
            logger.info(
                "Добавлена колонка salons.%s",
                column_name,
            )

        add_column_if_missing(
            "owner_id",
            "ALTER TABLE salons ADD COLUMN owner_id INTEGER NULL",
        )

        add_column_if_missing(
            "slug",
            "ALTER TABLE salons ADD COLUMN slug VARCHAR(100) NULL",
        )

        add_column_if_missing(
            "plan",
            (
                "ALTER TABLE salons "
                "ADD COLUMN plan VARCHAR(30) "
                "NOT NULL DEFAULT 'free'"
            ),
        )

        add_column_if_missing(
            "subscription_status",
            (
                "ALTER TABLE salons "
                "ADD COLUMN subscription_status VARCHAR(30) "
                "NOT NULL DEFAULT 'trial'"
            ),
        )

        add_column_if_missing(
            "trial_ends_at",
            "ALTER TABLE salons ADD COLUMN trial_ends_at TIMESTAMP NULL",
            "ALTER TABLE salons ADD COLUMN trial_ends_at DATETIME NULL",
        )

        add_column_if_missing(
            "subscription_ends_at",
            (
                "ALTER TABLE salons "
                "ADD COLUMN subscription_ends_at TIMESTAMP NULL"
            ),
            (
                "ALTER TABLE salons "
                "ADD COLUMN subscription_ends_at DATETIME NULL"
            ),
        )

        add_column_if_missing(
            "is_active",
            (
                "ALTER TABLE salons "
                "ADD COLUMN is_active BOOLEAN "
                "NOT NULL DEFAULT TRUE"
            ),
            (
                "ALTER TABLE salons "
                "ADD COLUMN is_active BOOLEAN "
                "NOT NULL DEFAULT 1"
            ),
        )

        add_column_if_missing(
            "created_at",
            (
                "ALTER TABLE salons "
                "ADD COLUMN created_at TIMESTAMP NULL"
            ),
            (
                "ALTER TABLE salons "
                "ADD COLUMN created_at DATETIME NULL"
            ),
        )

        add_column_if_missing(
            "updated_at",
            (
                "ALTER TABLE salons "
                "ADD COLUMN updated_at TIMESTAMP NULL"
            ),
            (
                "ALTER TABLE salons "
                "ADD COLUMN updated_at DATETIME NULL"
            ),
        )

        now = datetime.utcnow()
        trial_end = now + timedelta(days=14)

        connection.execute(
            text(
                """
                UPDATE salons
                SET slug = :slug_prefix || id
                WHERE slug IS NULL OR slug = ''
                """
            ),
            {"slug_prefix": "salon-"},
        )

        connection.execute(
            text(
                """
                UPDATE salons
                SET created_at = :now
                WHERE created_at IS NULL
                """
            ),
            {"now": now},
        )

        connection.execute(
            text(
                """
                UPDATE salons
                SET updated_at = :now
                WHERE updated_at IS NULL
                """
            ),
            {"now": now},
        )

        connection.execute(
            text(
                """
                UPDATE salons
                SET trial_ends_at = :trial_end
                WHERE subscription_status = 'trial'
                  AND trial_ends_at IS NULL
                """
            ),
            {"trial_end": trial_end},
        )

        # Назначаем владельца существующим салонам, если в users
        # уже есть owner/admin или хотя бы один пользователь.
        owner_id = connection.execute(
            text(
                """
                SELECT id
                FROM users
                ORDER BY
                    CASE
                        WHEN role = 'owner' THEN 0
                        WHEN role = 'admin' THEN 1
                        ELSE 2
                    END,
                    id
                LIMIT 1
                """
            )
        ).scalar_one_or_none()

        if owner_id is not None:
            connection.execute(
                text(
                    """
                    UPDATE salons
                    SET owner_id = :owner_id
                    WHERE owner_id IS NULL
                    """
                ),
                {"owner_id": owner_id},
            )

        if dialect == "postgresql":
            connection.execute(
                text(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS ix_salons_slug
                    ON salons (slug)
                    """
                )
            )

            connection.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS ix_salons_owner_id
                    ON salons (owner_id)
                    """
                )
            )

    logger.info("Схема базы данных успешно проверена и обновлена.")
