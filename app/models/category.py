from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint(
            "LENGTH(TRIM(name)) > 0",
            name="ck_categories_name_not_blank",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
    )

    icon: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )

    services = relationship(
        "Service",
        back_populates="category",
        passive_deletes=True,
    )
