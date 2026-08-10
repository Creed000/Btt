import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)
INDEX_NAME = "uq_master_schedule_master_weekday"


def upgrade_master_schedule_integrity() -> None:
    """
    Гарантирует одну строку расписания на master_id + weekday
    для уже существующих production-баз.

    Также проверяет, что weekday находится в диапазоне 0..6.
    Существующие данные автоматически не удаляются и не исправляются.
    """
    inspector = inspect(engine)

    if "master_schedules" not in inspector.get_table_names():
        return

    columns = {
        column["name"]
        for column in inspector.get_columns("master_schedules")
    }

    required = {"id", "master_id", "weekday"}
    missing = required - columns

    if missing:
        logger.warning(
            "Не удалось усилить master_schedules: отсутствуют колонки %s",
            ", ".join(sorted(missing)),
        )
        return

    with engine.begin() as connection:
        invalid_weekdays = connection.execute(
            text(
                """
                SELECT id, master_id, weekday
                FROM master_schedules
                WHERE weekday < 0 OR weekday > 6
                ORDER BY master_id, weekday, id
                LIMIT 20
                """
            )
        ).all()

        if invalid_weekdays:
            details = "; ".join(
                f"id={row.id}, master_id={row.master_id}, weekday={row.weekday}"
                for row in invalid_weekdays
            )
            raise RuntimeError(
                "В master_schedules найдены некорректные weekday. "
                "Допустимы только 0..6. "
                f"Найдены: {details}"
            )

        duplicates = connection.execute(
            text(
                """
                SELECT master_id, weekday, COUNT(*) AS duplicate_count
                FROM master_schedules
                GROUP BY master_id, weekday
                HAVING COUNT(*) > 1
                ORDER BY master_id, weekday
                LIMIT 20
                """
            )
        ).all()

        if duplicates:
            details = "; ".join(
                (
                    f"master_id={row.master_id}, weekday={row.weekday}, "
                    f"count={row.duplicate_count}"
                )
                for row in duplicates
            )
            raise RuntimeError(
                "Нельзя включить уникальность расписания: "
                "в БД уже есть дубли master_id + weekday. "
                f"Найдены: {details}"
            )

        if engine.dialect.name in {"postgresql", "sqlite"}:
            connection.execute(
                text(
                    f"""
                    CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_NAME}
                    ON master_schedules (master_id, weekday)
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

    logger.info(
        "Уникальность master_schedules(master_id, weekday) проверена."
    )
