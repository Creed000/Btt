from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Master(Base):
    __tablename__ = "masters"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        unique=True,
        nullable=False,
    )

    salon_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "salons.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    branch_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "branches.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    city_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "cities.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    description: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    slug: Mapped[str | None] = mapped_column(
        String(80),
        unique=True,
        index=True,
        nullable=True,
    )

    rating: Mapped[float] = mapped_column(
        default=5.0,
        nullable=False,
    )

    booking_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    user = relationship(
        "User",
        back_populates="master",
    )

    salon = relationship(
        "Salon",
        foreign_keys=[salon_id],
    )

    branch = relationship(
        "Branch",
        foreign_keys=[branch_id],
    )

    city = relationship(
        "City",
        back_populates="masters",
    )

    services = relationship(
        "Service",
        back_populates="master",
        cascade="all, delete-orphan",
    )
