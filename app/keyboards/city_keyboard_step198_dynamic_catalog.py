from sqlalchemy import and_, distinct, or_, select
from telegram import KeyboardButton, ReplyKeyboardMarkup

from app.database.session import SessionLocal
from app.models.city import City
from app.models.master import Master
from app.models.salon import Salon
from app.models.service import Service
from app.models.user import User
from app.services.timezone import local_naive_now


def city_menu() -> ReplyKeyboardMarkup:
    db = SessionLocal()

    try:
        now = local_naive_now()

        city_names = list(
            db.scalars(
                select(
                    distinct(City.name)
                )
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
                    City.name.asc()
                )
            ).all()
        )

        keyboard: list[list[KeyboardButton]] = [
            [
                KeyboardButton(
                    f"🏙 {city_name}"
                )
            ]
            for city_name in city_names
        ]

        if not keyboard:
            keyboard.append(
                [
                    KeyboardButton(
                        "Доступных городов нет"
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
            input_field_placeholder="Выберите город",
        )

    finally:
        db.close()
