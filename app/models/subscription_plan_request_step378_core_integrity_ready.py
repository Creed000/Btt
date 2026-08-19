from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class SubscriptionPlanRequest(Base):
    __tablename__ = "subscription_plan_requests"
    __table_args__ = (
        CheckConstraint(
            "current_plan IN ('free', 'basic', 'pro', 'business')",
            name="ck_subscription_plan_requests_current_plan_valid",
        ),
        CheckConstraint(
            "requested_plan IN ('free', 'basic', 'pro', 'business')",
            name="ck_subscription_plan_requests_requested_plan_valid",
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'replaced')",
            name="ck_subscription_plan_requests_status_valid",
        ),
        CheckConstraint(
            "(status = 'pending' AND resolved_at IS NULL) "
            "OR (status <> 'pending' AND resolved_at IS NOT NULL)",
            name="ck_subscription_plan_requests_resolved_state",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    salon_id: Mapped[int] = mapped_column(
        ForeignKey(
            "salons.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    requested_by_user_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    current_plan: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    requested_plan: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        server_default=text("'pending'"),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )

    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    salon = relationship(
        "Salon",
    )

    requested_by = relationship(
        "User",
    )
