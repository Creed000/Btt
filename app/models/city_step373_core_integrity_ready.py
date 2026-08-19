from sqlalchemy import Boolean, CheckConstraint, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class City(Base):
    __tablename__ = "cities"
    __table_args__ = (
        CheckConstraint(
            "LENGTH(TRIM(name)) > 0",
            name="ck_cities_name_not_blank",
        ),
        Index(
            "uq_cities_normalized_name",
            text("LOWER(TRIM(name))"),
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=text("true"),
        nullable=False,
    )

    masters = relationship(
        "Master",
        back_populates="city"
    )
