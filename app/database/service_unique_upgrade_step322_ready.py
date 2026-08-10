import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)

INDEX_NAME = "uq_services_master_normalized_title"


def upgrade_service_title_uniqueness() -> None:
    """
    Гарантирует на уровне БД:
    у одного мастера не может быть двух услуг с одинаковым
    названием без учёта регистра и пробелов по краям.
    """
    inspector = inspect(engine)

    if "services" not in inspector.get_table_names():
        return

    columns = {
        column["name"]
        for column in inspector.get_columns("services")
    }

    required = {"id", "master_id", "title"}
    missing = required - columns

    if missing:
        logger.warning(
            "Не удалось создать %s: в services не хватает колонок %s",
            INDEX_NAME,
            ", ".join(sorted(missing)),
        )
        return

    with engine.begin() as connection:
        duplicates = connection.execute(
            text(
                """
                SELECT
                    master_id,
                    LOWER(TRIM(title)) AS normalized_title,
                    COUNT(*) AS duplicate_count
                FROM services
                GROUP BY master_id, LOWER(TRIM(title))
                HAVING COUNT(*) > 1
                ORDER BY master_id, normalized_title
                """
            )
        ).all()

        if duplicates:
            details = "; ".join(
                f"master_id={row.master_id}, title={row.normalized_title!r}, count={row.duplicate_count}"
                for row in duplicates[:20]
            )

            raise RuntimeError(
                "Нельзя включить уникальность названий услуг: "
                "в БД уже есть дубли. Удалите или переименуйте лишние услуги. "
                f"Найдены: {details}"
            )

        dialect = engine.dialect.name

        if dialect in {"postgresql", "sqlite"}:
            connection.execute(
                text(
                    f"""
                    CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_NAME}
                    ON services (master_id, LOWER(TRIM(title)))
                    """
                )
            )
        else:
            logger.warning(
                "Диалект %s не поддержан для индекса %s.",
                dialect,
                INDEX_NAME,
            )
            return

    logger.info(
        "Уникальность названий услуг одного мастера проверена."
    )
