from sqlalchemy import CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Service(Base):
    __tablename__ = "services"
    __table_args__ = (
        CheckConstraint(
            "duration BETWEEN 15 AND 720",
            name="ck_services_duration_range",
        ),
        CheckConstraint(
            "price BETWEEN 0 AND 10000000",
            name="ck_services_price_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    master_id: Mapped[int] = mapped_column(
        ForeignKey("masters.id"),
        nullable=False,
    )

    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id"),
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    duration: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    price: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    master = relationship("Master", back_populates="services")
    category = relationship("Category", back_populates="services")
