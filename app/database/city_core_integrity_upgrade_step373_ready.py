import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)


def upgrade_city_core_integrity() -> None:
    """
    Укрепляет существующую таблицу cities в PostgreSQL.

    Гарантирует:
    - name NOT NULL;
    - name не пустой после TRIM;
    - is_active NOT NULL DEFAULT true;
    - нормализованная уникальность имени города.

    Повреждённые данные автоматически не исправляются.
    """
    inspector = inspect(engine)

    if "cities" not in inspector.get_table_names():
        logger.info(
            "Таблица cities ещё не создана. "
            "City core integrity upgrade пропущен."
        )
        return

    if engine.dialect.name != "postgresql":
        logger.info(
            "City core integrity upgrade пропущен для %s.",
            engine.dialect.name,
        )
        return

    columns = {
        column["name"]
        for column in inspector.get_columns("cities")
    }

    required = {"name", "is_active"}
    missing = sorted(required - columns)

    if missing:
        raise RuntimeError(
            "В cities отсутствуют обязательные поля: "
            + ", ".join(missing)
        )

    with engine.begin() as connection:
        broken = list(
            connection.execute(
                text(
                    """
                    SELECT id, name, is_active
                    FROM cities
                    WHERE name IS NULL
                       OR LENGTH(TRIM(name)) = 0
                       OR is_active IS NULL
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
                    f"name={row['name']!r} "
                    f"is_active={row['is_active']!r}"
                )
                for row in broken
            )
            raise RuntimeError(
                "Нельзя включить City core integrity: "
                "найдены NULL/пустые значения. "
                + details
            )

        duplicates = list(
            connection.execute(
                text(
                    """
                    SELECT
                        LOWER(TRIM(name)) AS normalized_name,
                        array_agg(id ORDER BY id) AS city_ids
                    FROM cities
                    GROUP BY LOWER(TRIM(name))
                    HAVING COUNT(*) > 1
                    ORDER BY normalized_name
                    LIMIT 50
                    """
                )
            ).mappings()
        )

        if duplicates:
            details = "; ".join(
                (
                    f"name={row['normalized_name']!r} "
                    f"City.id={list(row['city_ids'])}"
                )
                for row in duplicates
            )
            raise RuntimeError(
                "Нельзя включить нормализованную уникальность City.name: "
                "найдены дубли. "
                + details
            )

        connection.execute(
            text(
                "ALTER TABLE cities "
                "ALTER COLUMN name SET NOT NULL"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE cities "
                "ALTER COLUMN is_active SET DEFAULT true"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE cities "
                "ALTER COLUMN is_active SET NOT NULL"
            )
        )

        connection.execute(
            text(
                "ALTER TABLE cities "
                "DROP CONSTRAINT IF EXISTS ck_cities_name_not_blank"
            )
        )
        connection.execute(
            text(
                """
                ALTER TABLE cities
                ADD CONSTRAINT ck_cities_name_not_blank
                CHECK (LENGTH(TRIM(name)) > 0)
                """
            )
        )

        connection.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                    uq_cities_normalized_name
                ON cities (LOWER(TRIM(name)))
                """
            )
        )

    logger.info(
        "City core integrity включена."
    )
