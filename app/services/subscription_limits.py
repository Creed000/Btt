from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.models.master import Master
from app.models.salon import Salon


PLAN_LIMITS = {
    "free": {
        "masters": 1,
        "branches": 1,
    },
    "basic": {
        "masters": 3,
        "branches": 1,
    },
    "pro": {
        "masters": 10,
        "branches": 3,
    },
    "business": {
        "masters": 50,
        "branches": 10,
    },
}


def get_plan_limits(
    plan: str,
) -> dict[str, int]:
    return PLAN_LIMITS.get(
        plan,
        PLAN_LIMITS["free"],
    )


def get_salon_for_owner(
    db: Session,
    owner_id: int,
) -> Salon | None:
    return db.scalar(
        select(Salon).where(
            Salon.owner_id == owner_id,
            Salon.is_active.is_(True),
        )
    )


def count_salon_branches(
    db: Session,
    salon_id: int,
) -> int:
    return (
        db.scalar(
            select(func.count(Branch.id)).where(
                Branch.salon_id == salon_id,
            )
        )
        or 0
    )


def can_add_branch(
    db: Session,
    salon: Salon,
) -> tuple[bool, str]:
    limits = get_plan_limits(salon.plan)

    current_count = count_salon_branches(
        db,
        salon.id,
    )

    max_count = limits["branches"]

    if current_count >= max_count:
        return (
            False,
            (
                f"На тарифе {salon.plan} доступно "
                f"не более {max_count} филиалов."
            ),
        )

    return True, ""


def count_salon_masters(
    db: Session,
    salon_id: int,
) -> int:
    return (
        db.scalar(
            select(func.count(Master.id)).where(
                Master.salon_id == salon_id,
            )
        )
        or 0
    )


def count_active_salon_masters(
    db: Session,
    salon_id: int,
) -> int:
    return (
        db.scalar(
            select(func.count(Master.id)).where(
                Master.salon_id == salon_id,
                Master.booking_enabled.is_(True),
            )
        )
        or 0
    )


def can_add_master(
    db: Session,
    salon: Salon,
) -> tuple[bool, str]:
    limits = get_plan_limits(salon.plan)

    current_count = count_salon_masters(
        db,
        salon.id,
    )

    max_count = limits["masters"]

    if current_count >= max_count:
        return (
            False,
            (
                f"На тарифе {salon.plan} доступно "
                f"не более {max_count} мастеров."
            ),
        )

    return True, ""


def can_enable_master(
    db: Session,
    salon: Salon,
    master: Master,
) -> tuple[bool, str]:
    if master.salon_id != salon.id:
        return (
            False,
            "Мастер не принадлежит этому салону.",
        )

    if master.booking_enabled:
        return True, ""

    limits = get_plan_limits(salon.plan)

    active_count = count_active_salon_masters(
        db,
        salon.id,
    )

    max_count = limits["masters"]

    if active_count >= max_count:
        return (
            False,
            (
                f"На тарифе {salon.plan} одновременно могут "
                f"принимать записи не более {max_count} мастеров."
            ),
        )

    return True, ""
