import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)
INDEX_NAME = "uq_categories_normalized_name"


def upgrade_category_name_uniqueness() -> None:
    """
    Не допускает категории, отличающиеся только
    регистром или пробелами по краям.
    """
    inspector = inspect(engine)

    if "categories" not in inspector.get_table_names():
        return

    columns = {
        column["name"]
        for column in inspector.get_columns("categories")
    }

    required = {"id", "name"}
    missing = required - columns

    if missing:
        logger.warning(
            "Не удалось создать %s: в categories не хватает %s",
            INDEX_NAME,
            ", ".join(sorted(missing)),
        )
        return

    with engine.begin() as connection:
        duplicates = connection.execute(
            text(
                """
                SELECT
                    LOWER(TRIM(name)) AS normalized_name,
                    COUNT(*) AS duplicate_count
                FROM categories
                GROUP BY LOWER(TRIM(name))
                HAVING COUNT(*) > 1
                ORDER BY normalized_name
                """
            )
        ).all()

        if duplicates:
            details = "; ".join(
                f"name={row.normalized_name!r}, count={row.duplicate_count}"
                for row in duplicates[:20]
            )
            raise RuntimeError(
                "Нельзя включить уникальность категорий: "
                "в БД уже есть дубли по регистру/пробелам. "
                f"Найдены: {details}"
            )

        if engine.dialect.name in {"postgresql", "sqlite"}:
            connection.execute(
                text(
                    f"""
                    CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_NAME}
                    ON categories (LOWER(TRIM(name)))
                    """
                )
            )
        else:
            logger.warning(
                "Диалект %s не поддержан для индекса %s.",
                engine.dialect.name,
                INDEX_NAME,
            )
            return

    logger.info("Уникальность названий категорий проверена.")
