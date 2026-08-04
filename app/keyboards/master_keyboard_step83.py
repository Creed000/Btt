from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import joinedload
from telegram import KeyboardButton, ReplyKeyboardMarkup

from app.database.session import SessionLocal
from app.models.category import Category
from app.models.city import City
from app.models.master import Master
from app.models.salon import Salon
from app.models.service import Service
from app.models.user import User


def master_menu(
    city_name: str | None = None,
    category_name: str | None = None,
) -> ReplyKeyboardMarkup:
    db = SessionLocal()

    try:
        now = datetime.utcnow()

        query = (
            select(Master)
            .join(
                User,
                User.id == Master.user_id,
            )
            .outerjoin(
                Salon,
                Salon.id == Master.salon_id,
            )
            .options(
                joinedload(Master.user),
                joinedload(Master.city),
                joinedload(Master.salon),
            )
            .where(
                Master.booking_enabled.is_(True),
                Master.is_verified.is_(True),
                User.is_active.is_(True),
                or_(
                    # Самостоятельный мастер без салона.
                    Master.salon_id.is_(None),
                    # Мастер активного салона с действующей подпиской.
                    and_(
                        Salon.is_active.is_(True),
                        or_(
                            and_(
                                Salon.subscription_status == "trial",
                                or_(
                                    Salon.trial_ends_at.is_(None),
                                    Salon.trial_ends_at > now,
                                ),
                            ),
                            and_(
                                Salon.subscription_status == "active",
                                or_(
                                    Salon.subscription_ends_at.is_(None),
                                    Salon.subscription_ends_at > now,
                                ),
                            ),
                        ),
                    ),
                ),
            )
            .order_by(
                Master.rating.desc(),
                Master.id.asc(),
            )
        )

        if city_name:
            query = (
                query
                .join(
                    City,
                    Master.city_id == City.id,
                )
                .where(
                    City.name == city_name,
                    City.is_active.is_(True),
                )
            )

        if category_name:
            query = (
                query
                .join(
                    Service,
                    Service.master_id == Master.id,
                )
                .join(
                    Category,
                    Category.id == Service.category_id,
                )
                .where(
                    Category.name == category_name
                )
            )

        masters = list(
            db.scalars(query).unique().all()
        )

        keyboard: list[list[KeyboardButton]] = []

        for master in masters:
            name = (
                master.user.first_name
                if master.user and master.user.first_name
                else "Без имени"
            )

            city = (
                master.city.name
                if master.city
                else "Город не указан"
            )

            salon_name = (
                master.salon.name
                if master.salon
                else "Самостоятельный мастер"
            )

            keyboard.append(
                [
                    KeyboardButton(
                        f"👤 {name} · #{master.id} "
                        f"⭐ {master.rating:.1f} · {city} · {salon_name}"
                    )
                ]
            )

        if not keyboard:
            keyboard.append(
                [KeyboardButton("Подходящих мастеров нет")]
            )

        keyboard.append(
            [KeyboardButton("⬅️ Назад")]
        )

        return ReplyKeyboardMarkup(
            keyboard=keyboard,
            resize_keyboard=True,
            one_time_keyboard=False,
            input_field_placeholder="Выберите мастера",
        )

    finally:
        db.close()
