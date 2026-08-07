from sqlalchemy import Select, and_, exists, or_, select
from sqlalchemy.orm import joinedload

from app.models.category import Category
from app.models.city import City
from app.models.master import Master
from app.models.salon import Salon
from app.models.service import Service
from app.models.user import User
from app.services.timezone import local_naive_now


def available_masters_query(
    *,
    city_name: str | None = None,
    category_name: str | None = None,
) -> Select:
    now = local_naive_now()

    query = (
        select(Master)
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
        .options(
            joinedload(Master.user),
            joinedload(Master.city),
            joinedload(Master.salon),
            joinedload(Master.branch),
            joinedload(Master.services).joinedload(
                Service.category
            ),
        )
        .where(
            Master.booking_enabled.is_(True),
            Master.is_verified.is_(True),
            User.is_active.is_(True),
            Master.city_id.is_not(None),
            City.is_active.is_(True),
            exists(
                select(Service.id).where(
                    Service.master_id == Master.id
                )
            ),
            or_(
                # Индивидуальный мастер.
                Master.salon_id.is_(None),

                # Мастер салона.
                and_(
                    Master.salon_id.is_not(None),
                    Master.branch_id.is_not(None),
                    Salon.is_active.is_(True),
                    or_(
                        and_(
                            Salon.subscription_status
                            == "trial",
                            Salon.trial_ends_at.is_not(
                                None
                            ),
                            Salon.trial_ends_at > now,
                        ),
                        and_(
                            Salon.subscription_status
                            == "active",
                            Salon.subscription_ends_at.is_not(
                                None
                            ),
                            Salon.subscription_ends_at
                            > now,
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
        query = query.where(
            City.name == city_name
        )

    if category_name:
        query = query.where(
            exists(
                select(Service.id)
                .join(
                    Category,
                    Category.id
                    == Service.category_id,
                )
                .where(
                    Service.master_id
                    == Master.id,
                    Category.name
                    == category_name,
                )
            )
        )

    return query


def master_is_available(
    db,
    master_id: int,
    *,
    city_name: str | None = None,
    category_name: str | None = None,
) -> Master | None:
    return db.scalars(
        available_masters_query(
            city_name=city_name,
            category_name=category_name,
        ).where(
            Master.id == master_id
        )
    ).unique().first()
