from sqlalchemy import and_, distinct, or_, select
from telegram import KeyboardButton, ReplyKeyboardMarkup

from app.database.session import SessionLocal
from app.models.category import Category
from app.models.city import City
from app.models.master import Master
from app.models.salon import Salon
from app.models.service import Service
from app.models.user import User
from app.services.timezone import local_naive_now


CATEGORY_ICONS = {
    "Волосы": "💇",
    "Маникюр": "💅",
    "Ресницы": "👁",
    "Массаж": "💆",
}


def category_menu(
    city_name: str | None = None,
) -> ReplyKeyboardMarkup:
    db = SessionLocal()

    try:
        now = local_naive_now()

        query = (
            select(
                distinct(Category.name)
            )
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
                City.is_active.is_(True),
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
            .order_by(
                Category.name.asc()
            )
        )

        if city_name:
            query = query.where(
                City.name == city_name
            )

        category_names = list(
            db.scalars(
                query
            ).all()
        )

        keyboard: list[list[KeyboardButton]] = []

        for category_name in category_names:
            icon = CATEGORY_ICONS.get(
                category_name,
                "✨",
            )

            keyboard.append(
                [
                    KeyboardButton(
                        f"{icon} {category_name}"
                    )
                ]
            )

        if not keyboard:
            keyboard.append(
                [
                    KeyboardButton(
                        "Доступных категорий нет"
                    )
                ]
            )

        keyboard.append(
            [KeyboardButton("⬅️ Назад")]
        )

        return ReplyKeyboardMarkup(
            keyboard=keyboard,
            resize_keyboard=True,
            one_time_keyboard=False,
            input_field_placeholder="Выберите категорию",
        )

    finally:
        db.close()
