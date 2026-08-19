import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)


def upgrade_category_core_integrity() -> None:
    """
    Укрепляет существующую таблицу categories.

    Гарантирует:
    - name NOT NULL;
    - name не пустой после TRIM.

    Уникальность LOWER(TRIM(name)) остаётся за уже существующим
    category_unique_upgrade.
    """
    inspector = inspect(engine)

    if "categories" not in inspector.get_table_names():
        logger.info(
            "Таблица categories ещё не создана. "
            "Category core integrity upgrade пропущен."
        )
        return

    if engine.dialect.name != "postgresql":
        logger.info(
            "Category core integrity upgrade пропущен для %s.",
            engine.dialect.name,
        )
        return

    columns = {
        column["name"]
        for column in inspector.get_columns("categories")
    }

    if "name" not in columns:
        raise RuntimeError(
            "В categories отсутствует обязательная колонка name."
        )

    with engine.begin() as connection:
        broken = list(
            connection.execute(
                text(
                    """
                    SELECT id, name
                    FROM categories
                    WHERE name IS NULL
                       OR LENGTH(TRIM(name)) = 0
                    ORDER BY id
                    LIMIT 50
                    """
                )
            ).mappings()
        )

        if broken:
            details = "; ".join(
                f"id={row['id']} name={row['name']!r}"
                for row in broken
            )
            raise RuntimeError(
                "Нельзя включить Category core integrity: "
                "найдены NULL/пустые названия. "
                + details
                + ". Исправьте данные вручную и повторите запуск."
            )

        connection.execute(
            text(
                "ALTER TABLE categories "
                "ALTER COLUMN name SET NOT NULL"
            )
        )

        connection.execute(
            text(
                "ALTER TABLE categories "
                "DROP CONSTRAINT IF EXISTS ck_categories_name_not_blank"
            )
        )

        connection.execute(
            text(
                """
                ALTER TABLE categories
                ADD CONSTRAINT ck_categories_name_not_blank
                CHECK (LENGTH(TRIM(name)) > 0)
                """
            )
        )

    logger.info(
        "Category core integrity включена."
    )
