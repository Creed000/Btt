from sqlalchemy.orm import Session

from app.services.master_catalog import available_masters_query


EMPTY_CITY_BUTTON = "Доступных городов нет"
EMPTY_CATEGORY_BUTTON = "Доступных категорий нет"


CATEGORY_ICONS = {
    "Волосы": "💇",
    "Маникюр": "💅",
    "Ресницы": "👁",
    "Массаж": "💆",
}


def resolve_city_button(
    db: Session,
    button_text: str,
) -> str | None:
    if not button_text.startswith("🏙 "):
        return None

    city_name = button_text.removeprefix(
        "🏙 "
    ).strip()

    if not city_name:
        return None

    master = db.scalars(
        available_masters_query(
            city_name=city_name,
        )
    ).unique().first()

    if master is None:
        return None

    return city_name


def resolve_category_button(
    db: Session,
    button_text: str,
    city_name: str,
) -> str | None:
    text = button_text.strip()

    if not text or text == EMPTY_CATEGORY_BUTTON:
        return None

    masters = list(
        db.scalars(
            available_masters_query(
                city_name=city_name,
            )
        ).unique().all()
    )

    available_categories = {
        service.category.name
        for master in masters
        for service in master.services
        if service.category is not None
        and service.category.name
    }

    for category_name in available_categories:
        icon = CATEGORY_ICONS.get(
            category_name,
            "✨",
        )

        if text == f"{icon} {category_name}":
            return category_name

    return None
