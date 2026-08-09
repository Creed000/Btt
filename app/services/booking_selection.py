from sqlalchemy.orm import Session

from app.models.master import Master
from app.services.master_catalog import (
    available_category_names,
    available_masters_query,
)


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

    # Старая кнопка города считается валидной
    # только если прямо сейчас в городе существует
    # хотя бы один мастер из строгого каталога.
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
    text_value = button_text.strip()

    if (
        not text_value
        or text_value == EMPTY_CATEGORY_BUTTON
    ):
        return None

    # Используем тот же source of truth,
    # что и category_menu(). Это закрывает старые
    # Telegram-кнопки категорий, если услуга уже
    # стала невалидной или мастер недоступен.
    available_categories = set(
        available_category_names(
            db,
            city_name=city_name,
        )
    )

    for category_name in available_categories:
        icon = CATEGORY_ICONS.get(
            category_name,
            "✨",
        )

        if text_value == (
            f"{icon} {category_name}"
        ):
            return category_name

    return None


def selected_master_is_available(
    db: Session,
    master_id: int,
    city_name: str,
    category_name: str,
) -> bool:
    """
    Дополнительный helper для обработчиков,
    которым нужна булева проверка старой кнопки
    мастера без загрузки услуг.
    """
    master = db.scalars(
        available_masters_query(
            city_name=city_name,
            category_name=category_name,
        ).where(
            Master.id == master_id
        )
    ).unique().first()

    return master is not None
