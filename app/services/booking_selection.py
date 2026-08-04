from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.city import City
from app.models.master import Master
from app.models.salon import Salon
from app.models.service import Service
from app.models.user import User
from app.services.timezone import local_naive_now


EMPTY_CITY_BUTTON = "Доступных городов нет"
EMPTY_CATEGORY_BUTTON = "Доступных категорий нет"


def _available_master_conditions(
    now,
):
    return (
        Master.booking_enabled.is_(True),
        Master.is_verified.is_(True),
        User.is_active.is_(True),
        or_(
            Master.salon_id.is_(None),
            and_(
                Salon.is_active.is_(True),
                or_(
                    and_(
                        Salon.subscription_status == "trial",
                        Salon.trial_ends_at.is_not(None),
                        Salon.trial_ends_at > now,
                    ),
                    and_(
                        Salon.subscription_status == "active",
                        Salon.subscription_ends_at.is_not(None),
                        Salon.subscription_ends_at > now,
                    ),
                ),
            ),
        ),
    )


def resolve_city_button(
    db: Session,
    button_text: str,
) -> str | None:
    """
    Возвращает название доступного города из динамической кнопки.

    Пример:
    «🏙 Бишкек» -> «Бишкек»
    """
    text = button_text.strip()

    if text == EMPTY_CITY_BUTTON:
        return None

    if not text.startswith("🏙 "):
        return None

    city_name = text.removeprefix(
        "🏙 "
    ).strip()

    if not city_name:
        return None

    now = local_naive_now()

    city = db.scalar(
        select(City)
        .join(
            Master,
            Master.city_id == City.id,
        )
        .join(
            User,
            User.id == Master.user_id,
        )
        .join(
            Service,
            Service.master_id == Master.id,
        )
        .outerjoin(
            Salon,
            Salon.id == Master.salon_id,
        )
        .where(
            City.name == city_name,
            City.is_active.is_(True),
            *_available_master_conditions(now),
        )
        .limit(1)
    )

    if city is None:
        return None

    return city.name


def resolve_category_button(
    db: Session,
    button_text: str,
    city_name: str,
) -> str | None:
    """
    Возвращает название категории, доступной в выбранном городе.

    Иконка категории может быть любой:
    «👁 Ресницы» -> «Ресницы»
    «✨ Брови» -> «Брови»
    """
    text = button_text.strip()

    if text == EMPTY_CATEGORY_BUTTON:
        return None

    if " " not in text:
        return None

    category_name = text.split(
        " ",
        1,
    )[1].strip()

    if not category_name:
        return None

    now = local_naive_now()

    category = db.scalar(
        select(Category)
        .join(
            Service,
            Service.category_id == Category.id,
        )
        .join(
            Master,
            Master.id == Service.master_id,
        )
        .join(
            User,
            User.id == Master.user_id,
        )
        .join(
            City,
            City.id == Master.city_id,
        )
        .outerjoin(
            Salon,
            Salon.id == Master.salon_id,
        )
        .where(
            Category.name == category_name,
            City.name == city_name,
            City.is_active.is_(True),
            *_available_master_conditions(now),
        )
        .limit(1)
    )

    if category is None:
        return None

    return category.name
