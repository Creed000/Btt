import logging
from datetime import datetime, timedelta

from sqlalchemy import inspect, text

from app.database.base import Base
from app.database.session import engine

# Импорт моделей нужен, чтобы Base.metadata видел все таблицы.
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


def _index_names(table_name: str) -> set[str]:
    inspector = inspect(engine)

    if table_name not in inspector.get_table_names():
        return set()

    return {
        index["name"]
        for index in inspector.get_indexes(table_name)
        if index.get("name")
    }


def upgrade_database_schema() -> None:
    """
    Создаёт отсутствующие таблицы и безопасно добавляет SaaS-поля
    в существующие таблицы salons и masters.

    Функция идемпотентна: её можно запускать при каждом старте.
    """
    Base.metadata.create_all(bind=engine)

    dialect = engine.dialect.name

    salon_columns = _column_names("salons")
    master_columns = _column_names("masters")

    with engine.begin() as connection:
        def add_column_if_missing(
            table_name: str,
            known_columns: set[str],
            column_name: str,
            postgres_sql: str,
            sqlite_sql: str | None = None,
        ) -> None:
            if column_name in known_columns:
                return

            sql = (
                sqlite_sql
                if dialect == "sqlite" and sqlite_sql is not None
                else postgres_sql
            )

            connection.execute(text(sql))
            known_columns.add(column_name)

            logger.info(
                "Добавлена колонка %s.%s",
                table_name,
                column_name,
            )

        # ---------------------------------------------------------
        # Таблица salons
        # ---------------------------------------------------------
        if salon_columns:
            add_column_if_missing(
                "salons",
                salon_columns,
                "owner_id",
                "ALTER TABLE salons ADD COLUMN owner_id INTEGER NULL",
            )

            add_column_if_missing(
                "salons",
                salon_columns,
                "slug",
                "ALTER TABLE salons ADD COLUMN slug VARCHAR(100) NULL",
            )

            add_column_if_missing(
                "salons",
                salon_columns,
                "plan",
                (
                    "ALTER TABLE salons "
                    "ADD COLUMN plan VARCHAR(30) "
                    "NOT NULL DEFAULT 'free'"
                ),
            )

            add_column_if_missing(
                "salons",
                salon_columns,
                "subscription_status",
                (
                    "ALTER TABLE salons "
                    "ADD COLUMN subscription_status VARCHAR(30) "
                    "NOT NULL DEFAULT 'trial'"
                ),
            )

            add_column_if_missing(
                "salons",
                salon_columns,
                "trial_ends_at",
                "ALTER TABLE salons ADD COLUMN trial_ends_at TIMESTAMP NULL",
                "ALTER TABLE salons ADD COLUMN trial_ends_at DATETIME NULL",
            )

            add_column_if_missing(
                "salons",
                salon_columns,
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
                "salons",
                salon_columns,
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
                "salons",
                salon_columns,
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
                "salons",
                salon_columns,
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

        # ---------------------------------------------------------
        # Таблица masters
        # ---------------------------------------------------------
        if master_columns:
            add_column_if_missing(
                "masters",
                master_columns,
                "salon_id",
                "ALTER TABLE masters ADD COLUMN salon_id INTEGER NULL",
            )

            add_column_if_missing(
                "masters",
                master_columns,
                "branch_id",
                "ALTER TABLE masters ADD COLUMN branch_id INTEGER NULL",
            )

            # Для существующих мастеров пытаемся назначить салон владельца.
            # Поля остаются nullable, поэтому старые данные не ломаются.
            connection.execute(
                text(
                    """
                    UPDATE masters
                    SET salon_id = (
                        SELECT salons.id
                        FROM salons
                        JOIN users
                          ON users.id = salons.owner_id
                        WHERE users.id = masters.user_id
                        LIMIT 1
                    )
                    WHERE salon_id IS NULL
                    """
                )
            )

            # Если у салона есть главный филиал, назначаем его мастеру.
            connection.execute(
                text(
                    """
                    UPDATE masters
                    SET branch_id = (
                        SELECT branches.id
                        FROM branches
                        WHERE branches.salon_id = masters.salon_id
                        ORDER BY branches.id
                        LIMIT 1
                    )
                    WHERE branch_id IS NULL
                      AND salon_id IS NOT NULL
                    """
                )
            )

        # ---------------------------------------------------------
        # Индексы PostgreSQL
        # ---------------------------------------------------------
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

            connection.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS ix_masters_salon_id
                    ON masters (salon_id)
                    """
                )
            )

            connection.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS ix_masters_branch_id
                    ON masters (branch_id)
                    """
                )
            )

            # Добавляем внешние ключи только если их ещё нет.
            connection.execute(
                text(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1
                            FROM pg_constraint
                            WHERE conname = 'fk_masters_salon_id_salons'
                        ) THEN
                            ALTER TABLE masters
                            ADD CONSTRAINT fk_masters_salon_id_salons
                            FOREIGN KEY (salon_id)
                            REFERENCES salons(id)
                            ON DELETE SET NULL;
                        END IF;
                    END
                    $$;
                    """
                )
            )

            connection.execute(
                text(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1
                            FROM pg_constraint
                            WHERE conname = 'fk_masters_branch_id_branches'
                        ) THEN
                            ALTER TABLE masters
                            ADD CONSTRAINT fk_masters_branch_id_branches
                            FOREIGN KEY (branch_id)
                            REFERENCES branches(id)
                            ON DELETE SET NULL;
                        END IF;
                    END
                    $$;
                    """
                )
            )

    logger.info(
        "Схема базы данных успешно проверена и обновлена."
    )
