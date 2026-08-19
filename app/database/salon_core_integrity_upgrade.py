import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)


CORE_COLUMNS = (
    "owner_id",
    "name",
    "slug",
    "plan",
    "subscription_status",
    "is_active",
    "created_at",
    "updated_at",
)

VALID_PLANS = (
    "free",
    "basic",
    "pro",
    "business",
)

VALID_STATUSES = (
    "trial",
    "active",
    "expired",
    "cancelled",
)


def upgrade_salon_core_integrity() -> None:
    """
    Укрепляет существующую таблицу salons в PostgreSQL.

    Гарантирует:
    - обязательные core-поля NOT NULL;
    - name/slug не пустые;
    - только известные plan/subscription_status;
    - trial имеет trial_ends_at;
    - active имеет subscription_ends_at;
    - slug уникален без учёта регистра/пробелов.

    Повреждённые данные автоматически не исправляются.
    """
    inspector = inspect(engine)

    if "salons" not in inspector.get_table_names():
        logger.info(
            "Таблица salons ещё не создана. "
            "Salon core integrity upgrade пропущен."
        )
        return

    if engine.dialect.name != "postgresql":
        logger.info(
            "Salon core integrity upgrade пропущен для %s.",
            engine.dialect.name,
        )
        return

    columns = {
        column["name"]
        for column in inspector.get_columns("salons")
    }

    required = set(CORE_COLUMNS) | {
        "trial_ends_at",
        "subscription_ends_at",
    }

    missing_columns = sorted(required - columns)
    if missing_columns:
        raise RuntimeError(
            "В salons отсутствуют обязательные колонки: "
            + ", ".join(missing_columns)
        )

    with engine.begin() as connection:
        broken = list(
            connection.execute(
                text(
                    """
                    SELECT
                        id,
                        owner_id,
                        name,
                        slug,
                        plan,
                        subscription_status,
                        trial_ends_at,
                        subscription_ends_at
                    FROM salons
                    WHERE owner_id IS NULL
                       OR name IS NULL
                       OR LENGTH(TRIM(name)) = 0
                       OR slug IS NULL
                       OR LENGTH(TRIM(slug)) = 0
                       OR plan IS NULL
                       OR plan NOT IN ('free', 'basic', 'pro', 'business')
                       OR subscription_status IS NULL
                       OR subscription_status NOT IN (
                            'trial', 'active', 'expired', 'cancelled'
                       )
                       OR is_active IS NULL
                       OR created_at IS NULL
                       OR updated_at IS NULL
                       OR (
                            subscription_status = 'trial'
                            AND trial_ends_at IS NULL
                       )
                       OR (
                            subscription_status = 'active'
                            AND subscription_ends_at IS NULL
                       )
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
                    f"owner={row['owner_id']} "
                    f"plan={row['plan']!r} "
                    f"status={row['subscription_status']!r}"
                )
                for row in broken
            )
            raise RuntimeError(
                "Нельзя включить Salon core integrity: "
                "найдены некорректные строки. "
                + details
            )

        duplicate_slugs = list(
            connection.execute(
                text(
                    """
                    SELECT
                        LOWER(TRIM(slug)) AS normalized_slug,
                        array_agg(id ORDER BY id) AS salon_ids
                    FROM salons
                    GROUP BY LOWER(TRIM(slug))
                    HAVING COUNT(*) > 1
                    ORDER BY normalized_slug
                    LIMIT 50
                    """
                )
            ).mappings()
        )

        if duplicate_slugs:
            details = "; ".join(
                (
                    f"slug={row['normalized_slug']!r} "
                    f"Salon.id={list(row['salon_ids'])}"
                )
                for row in duplicate_slugs
            )
            raise RuntimeError(
                "Нельзя включить нормализованную уникальность "
                "Salon.slug: найдены дубли. "
                + details
            )

        for column_name in CORE_COLUMNS:
            connection.execute(
                text(
                    f"ALTER TABLE salons "
                    f"ALTER COLUMN {column_name} SET NOT NULL"
                )
            )

        constraint_sql = {
            "ck_salons_name_not_blank":
                "CHECK (LENGTH(TRIM(name)) > 0)",
            "ck_salons_slug_not_blank":
                "CHECK (LENGTH(TRIM(slug)) > 0)",
            "ck_salons_plan_valid":
                "CHECK (plan IN ('free', 'basic', 'pro', 'business'))",
            "ck_salons_subscription_status_valid":
                "CHECK (subscription_status IN "
                "('trial', 'active', 'expired', 'cancelled'))",
            "ck_salons_trial_requires_end":
                "CHECK (subscription_status <> 'trial' "
                "OR trial_ends_at IS NOT NULL)",
            "ck_salons_active_requires_end":
                "CHECK (subscription_status <> 'active' "
                "OR subscription_ends_at IS NOT NULL)",
        }

        for name, sql in constraint_sql.items():
            connection.execute(
                text(
                    f"ALTER TABLE salons "
                    f"DROP CONSTRAINT IF EXISTS {name}"
                )
            )
            connection.execute(
                text(
                    f"ALTER TABLE salons "
                    f"ADD CONSTRAINT {name} {sql}"
                )
            )

        connection.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                    uq_salons_slug_normalized
                ON salons (LOWER(TRIM(slug)))
                """
            )
        )

    logger.info(
        "Salon core integrity включена."
    )
