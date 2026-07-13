from sqlalchemy import Boolean, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Master(Base):
    __tablename__ = "masters"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        unique=True,
        nullable=False,
    )

    city_id: Mapped[int | None] = mapped_column(
        ForeignKey("cities.id"),
        nullable=True,
    )

    description: Mapped[str | None] = mapped_column(
        String(1000)
    )

    slug: Mapped[str | None] = mapped_column(
        String(80),
        unique=True,
        index=True,
        nullable=True,
    )

    rating: Mapped[float] = mapped_column(
        default=5.0
    )
    
    booking_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )
    
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )
    
    user = relationship(
        "User",
        back_populates="master",
    )

    city = relationship(
        "City",
        back_populates="masters"
    )

    services = relationship(
        "Service",
        back_populates="master",
        cascade="all, delete-orphan",
    )
